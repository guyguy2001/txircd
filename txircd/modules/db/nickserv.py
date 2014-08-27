from twisted.internet import reactor
from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData
from txircd.user import LocalUser
from zope.interface import implements

from dbservice import DBService


def getDonorID(user):
    """Helper function that returns the user's authenticated donor ID,
    or None if not authenticated."""
    return user.cache.get("accountid", None)


class NickServ(DBService):
    implements(IPlugin, IModuleData)

    name = "NickServ"

    user_cmd_aliases = {
        "NS": (10, None),
        "GHOST": (10, "GHOST"),
    }

    help = ("NickServ matches your IRC nickname to your Donor account, allowing for a painless auction process, "
           "as well as the peace of mind that nobody can use your nickname but you.\n"
           "You can run these commands with \x02/ns COMMAND\x02.")

    def load(self):
        super(NickServ, self).load()
        # Some explanation of the flow of checking a user's nick and how it works:
        # A nick check is started by a user registering, changing nick, logging out, or at module load.
        # A DB query and a timer are both started.
        # If the DB query shows that the nick is not protected, or that the user owns it, the timer is cancelled.
        # Once both the DB query and the timer have completed, the final conditions are checked:
        #     That the user does not own the nick
        #     That the user has not changed nicks again during this time
        # then the user's nick is forced to change.
        # This dict maps (user, nick) to (timer, owners), where owners is a list of owning donorIDs,
        # or None if not known yet (note that an empty list means nick is unowned).
        # Note that if checkNick tries to start a check on an already pending (user, nick),
        # it is ignored - this prevents someone from being able to repeatedly switch nicks
        # and keep the timer pending.
        self.nick_checks = {}
        for user in self.ircd.users.values():
            self.checkNick(user)

    def serviceCommands(self):
        return {
            "ID": (self.handleLogin, False, "This is an alias for LOGIN",
                   "USAGE: \x02ID email password\n"
                   "ALTERNATE: \x02ID email:password\n"
                   "This command is an alias for LOGIN, for compatibility with some clients."),
            "IDENTIFY": (self.handleLogin, False, "This is an alias for LOGIN",
                         "USAGE: \x02IDENTIFY email password\n"
                         "ALTERNATE: \x02IDENTIFY email:password\n"
                         "This command is an alias for LOGIN, for compatibility with some clients."),
            "LOGIN": (self.handleLogin, False, "Log into your donor account",
                      "USAGE: \x02LOGIN email password\n"
                      "ALTERNATE: \x02LOGIN email:password\n"
                      "Log into the donor account specified by email with the given password. "
                      "The first form (with a space) is preferred, the other form is available "
                      "for compatability with some clients. If it isn't already, your current nick "
                      "will be associated with the account and protected from impersonation."),
            "LOGOUT": (self.handleLogout, False, "Log out of your donor account",
                       "USAGE: \x02LOGOUT\x02\n"
                       "Log out of whatever account you're currently logged in to. "
                       "Useful to prevent your roommate from bidding on auctions in your name."),
            "GHOST": (self.handleGhost, False, "Disconnect another user who is authenticated as you",
                      "USAGE: \x02GHOST nick\x02\n"
                      "Disconnects the given user, but only if they previously authenticated as you. "
                      "This lets you clean up after malfunctioning or remote clients and reclaim your "
                      "preferred nick."),
            "ADD": (self.handleAdd, False, "Add a nick to your account",
                    "USAGE: \x02ADD nick\n"
                    "Associates the given nick with your account, reserving it for your use only."),
            "DROP": (self.handleDrop, False, "Unregisters a nick from your account",
                     "USAGE: \x02DROP nick\n"
                     "Unregisters the given nick from your account, allowing others to use it "
                     "and giving you more space to register other nicks instead."),
            "NICKLIST": (self.handleNickList, False, "List nicks owned by your account",
                         "USAGE: \x02NICKLIST\n"
                         "Lists all nicks owned by your account."),
        }

    def actions(self):
        return super(NickServ, self).actions() + [
            ("welcome", 10, self.checkNick),
            ("changenick", 10, lambda user, oldNick, fromServer: self.checkNick(user)),
            ("changenick", 10, self.registerOnChange),
        ]

    def getConfig(self):
        return self.ircd.config.getWithDefault("nickserv", {})

    def handleLogin(self, user, params):
        try:
            if len(params) == 1:
                email, password = params[0].split(':', 1)
            else:
                email, password = params[:2]
        except ValueError:
            self.tellUser(user, "USAGE: \x02LOGIN email password")
            return

        if getDonorID(user):
            self.tellUser(user, "You're already logged in! You may want to LOGOUT first.")

        self.queryGetOne(
            lambda result: self.verifyLogin(user, password, result),
            self.reportError(user, "Server failure while trying to authenticate. Please try again later."),
            "SELECT id, display_name, password FROM donors WHERE email = %s",
            email)

    def verifyLogin(self, user, password, result):
        if 'compare-pbkdf2' not in self.ircd.functionCache:
            self.tellUser(user, "The server cannot authenticate due to an admin error")
            return

        if not result:
            self.tellUser(user, "The login credentials you provided were incorrect")
            return
        donorID, displayName, correctHash = result

        if not self.ircd.functionCache["compare-pbkdf2"](password, correctHash):
            self.tellUser(user, "The login credentials you provided were incorrect")
            return

        self.loginUser(user, displayName, donorID)

    def loginUser(self, user, displayName, donorID):
        # action "user-login" fires one a user is authenticated but before login happens
        # it takes args (user, displayName, donorID) and may return False to deny login
        denied = self.ircd.runActionUntilFalse("user-login", user, displayName, donorID)
        if denied:
            self.tellUser(user, "The login credentials you provided were incorrect")
            return

        user.cache["accountid"] = donorID
        if not displayName:
            displayName = "Anonymous"
        user.setMetadata("ext", "accountname", displayName.replace(" ", "_"))
        self.tellUser(user, "You are now identified. Welcome, {}".format(displayName))

        self.registerNick(user, user.nick, ignoreAlreadyRegistered=True)

    def handleAdd(self, user, params):
        if not params:
            self.tellUser(user, "USAGE: \x02ADD nick")
            return
        if not getDonorID(user):
            self.tellUser(user, "Cannot add nick: You aren't logged in")
            return
        nick = params[0]
        self.registerNick(user, nick)

    def registerNick(self, user, newNick, ignoreAlreadyRegistered=False):
        """Associate nick with logged in user.
        If ignoreAlreadyRegistered, don't emit errors for already registered nicks."""
        genericErrorMessage = ("Warning: Due to a server error, we can't register this nick. "
                               "Please inform a mod and try again later.")

        donorID = getDonorID(user)
        if not donorID:
            raise ValueError("User is not authenticated")
        maxNicks = self.getConfig().get("nick_limit", None)

        if newNick in self.genForceNicks(user):
            return # cannot register forced nicks

        def gotNicks(results):
            # Note that throughout this service we treat a nick as possibly having multiple owners,
            # even though we don't allow this. This is because it is technically possible in the database,
            # and we should try to act correctly no matter what the data says.
            myNicks = [nick for donor, nick in results if donor == donorID]
            nickOwners = [donor for donor, nick in results if nick == newNick]
            if newNick in myNicks:
                if not ignoreAlreadyRegistered:
                    self.tellUser(user, "The nick {} is already registered to your account".format(newNick))
                return
            if nickOwners:
                self.tellUser(user, "The nick {} is already owned by someone else".format(newNick))
                return
            if maxNicks is not None and len(myNicks) >= maxNicks:
                self.tellUser(user, "You already have {} registered nicks, so {} will not be protected.".format(
                              len(myNicks), newNick))
                return
            self.query(insertSuccess,
                       self.reportError(user, genericErrorMessage),
                       "INSERT INTO ircnicks(donor_id, nick) VALUES (%s, %s)",
                       donorID, newNick)

        def insertSuccess(result):
            self.tellUser(user, ("Nickname {} is now registered to your account "
                                 "and can not be used by any other user.").format(newNick))

        self.query(gotNicks,
                   self.reportError(user, genericErrorMessage),
                   "SELECT donor_id, nick FROM ircnicks WHERE donor_id = %s OR nick = %s",
                   donorID, newNick)

    def registerOnChange(self, user, oldNick, fromServer):
        if getDonorID(user):
            self.registerNick(user, user.nick, ignoreAlreadyRegistered=True)

    def handleDrop(self, user, params):
        if not params:
            self.tellUser(user, "USAGE: \x02DROP nick")
            return

        dropNick = params[0]
        donorID = getDonorID(user)
        genericErrorMessage = ("Warning: Due to a server error, we couldn't drop this nick. "
                               "Please inform a mod and try again later.")

        if not donorID:
            self.tellUser(user, "Cannot drop nick: You aren't logged in")
            return

        def checkOwned(result):
            if not result:
                self.tellUser(user, "You don't own the nick {}".format(dropNick))
                return
            self.query(deleteSuccess,
                       self.reportError(user, genericErrorMessage),
                       "DELETE FROM ircnicks WHERE donor_id = %s AND nick = %s",
                       donorID, dropNick)

        def deleteSuccess(result):
            self.tellUser(user, "Dropped nick {} from your account".format(dropNick))
            if dropNick == user.nick:
                self.checkNick(user)

        self.query(checkOwned,
                   self.reportError(user, genericErrorMessage),
                   "SELECT 1 FROM ircnicks WHERE donor_id = %s AND nick = %s",
                   donorID, dropNick)

    def checkNick(self, user):
        """Start timer for registered nick change.
        At the same time, start sql query checking if nick is registered.
        """
        nick = user.nick # save it here in case it changes

        if nick in self.genForceNicks(user):
            return # ignore generated nicks
        if isinstance(user, LocalUser):
            return # LocalUsers are trusted - they don't need auth

        # callbacks
        def timerComplete():
            timer, owners = self.nick_checks[user, nick]
            if owners is not None:
                bothComplete()

        def queryComplete(results):
            timer, owners = self.nick_checks[user, nick]
            owners = [owner for owner, in results]
            if not owners or getDonorID(user) in owners:
                # nick is not protected, or nick is owned by user
                timer.cancel()
                del self.nick_checks[user, nick]
                return
            self.nick_checks[user, nick] = timer, owners
            self.tellUser(user, "This is a registered nick. Please use \x02/msg NickServ login EMAIL PASSWORD\x02 "
                                "to verify your identity", split=False)
            if not timer.active():
                bothComplete()

        def bothComplete():
            # by the time we've reached here, the timer has fired and the query
            # has determined that the nick is protected. We check whether the user
            # owns the nick (in case they authenticated between the query finish and the timer fire)
            # and whether they haven't changed off it, then we force a nick change.
            timer, owners = self.nick_checks.pop((user, nick))
            if getDonorID(user) in owners:
                return # they are owner
            if user.nick != nick:
                return # they already changed
            if user.uuid not in self.ircd.users:
                return # they disconnected
            self.forceNick(user)

        def queryFailed(failure):
            timer, owners = self.nick_checks.pop((user, nick))
            timer.cancel()
            if user.nick != nick:
                return # they already changed
            if user.uuid not in self.ircd.users:
                return # they disconnected
            if not self.getConfig().get("allow_all_on_db_failure", False):
                self.tellUser(user, "Sorry, something went wrong. I'm not sure if you are who you say you are. "
                                    "Please inform a mod and the problem will be fixed shortly.")
                self.forceNick(user)

        if (user, nick) in self.nick_checks:
            return # user switched BACK to a nick that's still being timed

        timeout = self.getConfig().get("nick_timeout", 5)
        timer = reactor.callLater(timeout, timerComplete)

        self.query(queryComplete, queryFailed,
                   "SELECT donor_id FROM ircnicks WHERE nick = %s", nick)

        self.nick_checks[user, user.nick] = (timer, None)

    def genForceNicks(self, user):
        prefix = self.getConfig().get("guest_prefix", "")
        if prefix:
            return [prefix + user.uuid, user.uuid]
        return [user.uuid]

    def forceNick(self, user):
        for nick in self.genForceNicks(user):
            if nick not in self.ircd.userNicks:
                user.changeNick(nick)
                return
        assert False, "Failed to force nick change - user's uuid was already taken?"

    def handleLogout(self, user, params):
        if getDonorID(user):
            del user.cache["accountid"]
            self.tellUser(user, "You are now logged out.")
            self.checkNick(user)
        else:
            self.tellUser(user, "You are currently not logged in.")

    def handleGhost(self, user, params):
        if not params:
            self.tellUser(user, "USAGE: \x02GHOST nick\x02")
            return
        nick = params[0]
        donorID = getDonorID(user)
        if not donorID:
            self.tellUser(user, "You can't ghost anyone until you're logged in")
            return
        if nick not in self.ircd.userNicks:
            self.tellUser(user, "No such nick: {}".format(nick))
            return
        target = self.ircd.users[self.ircd.userNicks[nick]]
        if donorID != getDonorID(target):
            self.tellUser(user, "That user does not appear to be yours")
            return
        if target is user:
            self.tellUser(user, "You can't ghost yourself")
            return
        target.disconnect("Killed (GHOST command issued by {})".format(user.nick))

    def handleNickList(self, user, params):
        donorID = getDonorID(user)
        if not donorID:
            self.tellUser(user, "You can't list nicks, you aren't logged in.")

        def gotNicks(results):
            nicks = [nick for nick, in results]
            if not nicks:
                message = "You have no registered nicks."
            else:
                message = "Registered nicks: {}".format(", ".join(nicks))
            self.tellUser(user, message)

        self.query(gotNicks,
                   self.reportError(user, "Failed to get a list of nicks due to server error"),
                   "SELECT nick FROM ircnicks WHERE donor_id = %s",
                   donorID)

nickServ = NickServ()
