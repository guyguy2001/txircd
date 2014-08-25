from twisted.plugin import IPlugin
from twisted.python import log
from txircd.module_interface import IModuleData
from zope.interface import implements
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from traceback import format_exc
import itertools, logging, os, yaml

from dbservice import DBService


class BidServ(DBService):
    implements(IPlugin, IModuleData)

    name = "BidServ"
    user_cmd_aliases = {
        "BID": (10, "BID"),
        "BS": (10, None),
    }
    help = ("This service manages auctions - what the prize is, who can bid, "
            "tracks the bids and records the results on the backend.\n"
            "You can run these commands with \x02/bs COMMAND\x02.")

    auction = None
    starting = False

    def load(self):
        super(BidServ, self).load()
        if "bidserv" not in self.ircd.storage:
            self.ircd.storage["bidserv"] = {}
        auction = self.getAuction()
        if auction:
            message = ("\x02\x034Resuming auction for item #{auction[id]} (\"{auction[name]}\")\n"
                       "\x02\x034Current high bid is ${bid[value]:,} by {bid[donorName]}"
                      ).format(auction=auction, bid=self.getHighBid())
            self.broadcast(message)

    def serviceCommands(self):
        return {
            "START": (self.startAuction, True, "Begin the auction for the given prize id",
                      "USAGE: \x02START <prize id>\x02\n"
                      "Begin the auction for the prize with the given id.\n"
                      "Only one auction may happen at a time."),
            "STOP": (self.stopAuction, True, "Cancel a running auction",
                     "USAGE: \x02STOP\x02\n"
                     "Cancel a running auction, resetting all bids and keeping the item available."),
            "BID": (self.handleBid, False, "Make a bid on the current auction",
                    "USAGE: \x02BID <amount> [<smack talk>]\x02\n"
                    "Place a bid for the given amount (with or without a $ in front) on the current item. "
                    "Optionally, add some smack talk to taunt and demoralize your opponents!"),
            "REVERT": (self.handleRevert, True, "Undo the most recent bid",
                       "USAGE: \x02REVERT\x02\n"
                       "Remove the latest bid as though it didn't happen. "
                       "The previous high bid will be reinstated, and the going once/twice counter reset."),
            "ONCE": (self.goOnce, True, "Call the auction as Going Once",
                       "USAGE: \x02ONCE\x02\n"
                       "Call the current auction as Going Once. This can only be done when the auction "
                       "is not Going Anything yet."),
            "TWICE": (self.goTwice, True, "Call the auction as Going Twice",
                       "USAGE: \x02TWICE\x02\n"
                       "Call the current auction as Going Twice. This can only be done when the auction "
                       "is already Going Once."),
            "SOLD": (self.goSold, True, "Call the auction as Sold to the current top bidder!",
                     "USAGE: \x02SOLD\x02\n"
                     "Call the current auction as Sold. The current high bid will be recorded as the winner. "
                     "This can only be done when the auction is already Going Twice."),
            "HIGHBIDDER": (self.tellHighBid, False, "Find out what the current high bid is",
                           "Using this command will send you back the current highest bid for this auction."),
            "CURRENTAUCTION": (self.tellAuction, False, "Find out what the current auction is",
                           "Using this command will send you back some information on the current auction."),
        }

    def getIdentityInfo(self):
        return self.getConfig()

    def toDecimal(self, value):
        """Converts value (string, int, float or Decimal) to a 2-digit precision Decimal"""
        value = Decimal(str(value))
        # quantize operations on infinity throws an exception
        if value.is_finite():
            value = value.quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
        return value

    def toBid(self, value, donorID, donorName):
        """Converts values into a bid dict"""
        return {
            "value": value,
            "donorID": donorID,
            "donorName": donorName,
        }

    def getConfig(self):
        return self.ircd.config.getWithDefault("bidserv", {})

    def getAuction(self):
        # We need to get a "fresh" auction dict from ircd.storage every time,
        # as it stops watching existing references every time it does a sync()
        return self.ircd.storage["bidserv"]

    def getIncrement(self):
        value = self.getConfig().get("min_increment", "5")
        return self.toDecimal(value)

    def getHighBid(self):
        auction = self.getAuction()
        if not auction:
            return None
        if not auction["bids"]:
            return self.toBid(auction["startingBid"], None, "Nobody")
        return max(auction["bids"], key=lambda bid: bid["value"])

    def getLogFile(self, prizeID, stopped=False, extra=0):
        path = self.getConfig().get("logDirectory", ".")
        stop_str = "_stopped" if stopped else ""
        extra = ".{}".format(extra) if extra else ""
        return os.path.join(path, "auction{}-{}{}.log".format(stop_str, prizeID, extra))

    def logAuction(self, user=None, stopped=False):
        """Write log file for current auction. user is user to report errors to."""
        logPath = None
        auction = self.getAuction()
        try:
            # find a non-existent filename
            for n in itertools.count():
                logPath = self.getLogFile(auction["id"], stopped=stopped, extra=n)
                if not os.path.exists(logPath):
                    break
            with open(logPath, "w") as logFile:
                yaml.dump(auction, logFile)
        except (OSError, IOError):
            log.msg("Error while writing log ({!r}) for auction:\n{}".format(logPath, format_exc(),
                    logLevel=logging.warning))
            if user:
                self.tellUser(user, "Warning: Failed to write log for auction")

    def broadcast(self, message):
        """Send message to all channels"""
        for channel in self.ircd.channels.itervalues():
            channel.sendMessage("PRIVMSG", ":{}".format(message), sourceuser=self.user)

    def determineMadness(self, oldBid, newBid):
        levels = sorted(self.getConfig().get("madnessLevels", []))
        messages = [message for amount, message in levels if amount > oldBid and amount < newBid]
        if not self.getConfig().get("showAllMadness", False):
            messages = messages[-1:] # last one only
        return messages

    def startAuction(self, user, params):
        if self.getAuction():
            self.tellUser(user, "Cannot start auction: An auction is already in progress")
            return
        if self.starting:
            self.tellUser(user, "Cannot start auction: An auction is already in the process of starting")
            return
        if len(params) != 1:
            self.tellUser(user, "Wrong number of parameters. USAGE: \x02START <prize id>\x02")
            return
        prizeID = params[0]
        try:
            prizeID = int(prizeID)
        except ValueError:
            self.tellUser(user, "Bad prize id: {} is not a number".format(prizeID))
            return

        self.starting = True
        def onError(failure):
            self.starting = False
            self.reportError(user, detail=True)(failure)
        self.queryGetOne(
            lambda data: self.startedAuction(user, prizeID, data),
            onError,
            "SELECT name, sold, starting_bid FROM prizes WHERE id = %s",
            prizeID,
        )

    def startedAuction(self, user, prizeID, data):
        self.starting = False
        auction = self.getAuction()
        if not data:
            self.tellUser(user, "Cannot start auction: Prize id {} does not exist".format(prizeID))
            return
        name, sold, startingBid = data
        if sold:
            self.tellUser(user, "Cannot start auction: Prize {} has already been sold".format(prizeID))
            return
        startingBid = self.toDecimal(startingBid)
        auction.update({
            "id": prizeID,
            "name": name,
            "startingBid": startingBid,
            "bids": [],
            "called": 0,
        })

        message = (
            "\x02\x034Starting Auction for Lot #{auction[id]}: \"{auction[name]}\"\x02 - Called by {caller}\n"
            "\x02\x034Item info at http://desertbus.org/live-auction/{auction[id]}\n"
            "\x02\x034Make bids with \x1F/bid ###.## [smack talk]\n"
            "\x02\x034The minimum increment between bids is ${increment:,}\n"
            "\x02\x034Only registered donors can bid - https://donor.desertbus.org/\n"
            "\x02\x034Please do not make any fake bids\n"
            "\x02\x034Beginning bidding at ${auction[startingBid]:,}"
        ).format(increment=self.getIncrement(), caller=user.nick, auction=auction)
        # we could use splitMessage here but it might screw up the formatting
        for line in message.splitlines():
            self.broadcast(line)

        self.tellUser(user, "Auction successfully started")

    def stopAuction(self, user, params):
        auction = self.getAuction()
        if not auction:
            self.tellUser(user, "No auction is currently running")
            return
        self.logAuction(user, stopped=True)
        message = "\x02\x034Auction for {} canceled.\x02 - Called by {}".format(auction["name"], user.nick)
        self.broadcast(message)
        auction.clear()
        self.tellUser(user, "Auction successfully cancelled")

    def handleBid(self, user, params):
        auction = self.getAuction()
        if not params:
            self.tellUser(user, "Usage: \x02BID \x1Famount\x1F \x1F[smack talk]")
            return
        if not auction:
            self.tellUser(user, "There is not an auction going on right now")
            return

        # TODO get user's donorID (presumably NickServ populates user.cache with it?)
        # THIS IS A PLACEHOLDER until we can get the proper donor ids from NickServ
        donorID = hash(user.nick) % 2**10

        newBid = params[0].lstrip('$').replace(',', '') # allow stuff like "$1,000"
        smackTalk = " ".join(params[1:])[:250]

        try:
            newBid = self.toDecimal(newBid)
        except (ValueError, InvalidOperation):
            self.tellUser(user, "Sorry, {} is not a valid number".format(newBid))
            return

        special_rejects = {
            ("sNaN", "NaN"): "Sorry, NaN is not a number. Who'd have thought?",
            ("-Infinity", "-Normal", "-Subnormal"): "Sorry, you can't bid negative amounts. Nice try though.",
            ("-Zero", "+Zero"): "Hey, you need to bid \x02something\x02!",
            ("+Infinity",): "Heh heh, sure. You know what, I bid Infinity plus more than whatever you say! So there!"
        }
        number_class = newBid.number_class()
        for classes, message in special_rejects.iteritems():
            if number_class in classes:
                self.tellUser(user, message)
                return
        assert number_class in ("+Subnormal", "+Normal"), "Unknown number class for {!r}: {}".format(newBid, number_class)

        if newBid > self.getConfig().get("maxBid", Decimal("inf")):
            self.tellUser(user, ("Let's be honest, here.  You don't really have ${:,}, do you? "
                                 "I mean, do you \x02really\x02 have that much money on you?").format(newBid))
            return

        currentBid = self.getHighBid()
        if newBid <= currentBid["value"]:
            self.tellUser(user, "The high bid is already ${}".format(currentBid["value"]))
            return

        increment = self.getIncrement()
        if newBid < currentBid["value"] + increment:
            self.tellUser(user, "The minimum mid increment is ${:,} (you must bid at least ${:,})".format(
                                increment, currentBid["value"] + increment))
            return

        extras = self.determineMadness(currentBid["value"], newBid)
        if donorID == currentBid["donorID"]:
            extras.append(self.getConfig().get("spaceBid", "SPACE BID"))
        extras = "".join(["{}! ".format(extra) for extra in extras])
        message = "\x02\x034{}{} has the high bid of ${:,}! \x0312{}".format(extras, user.nick, newBid, smackTalk)

        auction["called"] = 0
        auction["bids"].append(self.toBid(newBid, donorID, user.nick))

        self.broadcast(message)

    def handleRevert(self, user, params):
        auction = self.getAuction()
        if not auction:
            self.tellUser(user, "There is not an auction going on right now")
            return
        if not auction["bids"]:
            self.tellUser(user, "No bids have been made yet!")
        badBid = self.getHighBid()
        auction["bids"].remove(badBid)
        newBid = self.getHighBid()
        auction["called"] = 0
        message = ("\x02\x034Bid for ${badBid[value]:,} by {badBid[donorName]} removed. "
                   "The new highest bid is for ${newBid[value]:,} by {newBid[donorName]}!"
                   "\x02 - Called by {caller}").format(badBid=badBid, newBid=newBid, caller=user.nick)
        self.broadcast(message)

    def goingCall(self, going, user):
        auction = self.getAuction()
        def getGoingName(called):
            return {
                0: "Not going anything",
                1: "Going Once",
                2: "Going Twice",
                3: "Sold",
            }[called]
        if not auction:
            self.tellUser(user, "There is not an auction going on right now")
            return False
        if auction["called"] != going - 1:
            self.tellUser(user, "Now is not the time to call {}.  (Current state: {})".format(
                                getGoingName(going), getGoingName(auction["called"])))
            return False
        auction["called"] = going
        highBid = self.getHighBid()
        message = "\x02\x034{}! To {} for ${:,}!\x02 - Called by {}".format(
                  getGoingName(going), highBid["donorName"], highBid["value"], user.nick)
        self.broadcast(message)
        return True

    def goOnce(self, user, params):
        self.goingCall(1, user)

    def goTwice(self, user, params):
        self.goingCall(2, user)

    def goSold(self, user, params):
        auction = self.getAuction()
        if not self.goingCall(3, user):
            return
        self.logAuction(user)
        winningBid = self.getHighBid()
        prizeID = auction["id"]
        # TODO do this check with a loop over all users looking for winningBid["donorID"] instead
        if winningBid["donorName"] in self.ircd.userNicks:
            winner = self.ircd.users[self.ircd.userNicks[winningBid["donorName"]]]
            winMessage = ("Congratulations! You won \"{}\"! "
                          "Please log into your donor account and visit "
                          "https://desertbus.org/donate?type=auction&prize={} to pay for your prize."
                         ).format(auction["name"], prizeID)
            self.tellUser(winner, winMessage)
        auction.clear()
        self.ircd.storage.sync() # we really don't want an item marked as sold in the DB with an ongoing auction
        successMessage = "Database updated - Item #{} sold for ${:,}!".format(prizeID, winningBid["value"])
        errorMessage = ("An error occurred updating the database with the winner for #{prizeID} "
                        "({donorName} with ID {donorID} for amount ${value:,})").format(prizeID=prizeID, **winningBid)
        self.query(lambda result: self.tellUser(user, successMessage),
                   self.reportError(user, errorMessage, detail=True),
                   "UPDATE prizes SET donor_id = %s, sold_amount = %s, sold = 1 WHERE id = %s",
                   winningBid["donorID"], winningBid["value"], prizeID)

    def tellHighBid(self, user, params):
        if not self.getAuction():
            self.tellUser(user, "There is not an auction going on right now")
            return
        self.tellUser(user, "The current high bid is ${value:,} by {donorName}".format(**self.getHighBid()))

    def tellAuction(self, user, params):
        auction = self.getAuction()
        if not auction:
            self.tellUser(user, "There is not an auction going on right now")
            return
        self.tellUser(user, ("The item currently up for auction is lot #{id} ({name}). "
                            "http://desertbus.org/live-auction/{id}").format(**auction))


bidServ = BidServ()
