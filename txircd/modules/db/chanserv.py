from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData
from txircd.utils import ircLower, ModeType
from zope.interface import implements

from dbservice import DBService
from nickserv import getDonorID


class ChanServ(DBService):
    implements(IPlugin, IModuleData)

    name = "ChanServ"
    user_cmd_aliases = {
        "CS": (10, None),
        "CHANSERV": (10, None)
    }
    help = ("ChanServ can be used to register a channel, as well as keeping the topic and set modes even"
            "after all users in the channel have left.\n"
            "You can run these commands with \x02/cs COMMAND\x02.")


    def serviceCommands(self):
        return {
            "REGISTER": (self.handleRegister, False, "Register a channel that you control",
                         "USAGE: \x02REGISTER channel\n"
                         "Register a channel with chanserv, so that it will be restored with the same topic "
                         "and modes if it ever ceases to exist (for example, on a network restart). "
                         "You must be logged in to do this, and will be recorded as the founder of this channel. "
                         "You must be an op or better in the channel in order to register it."),
            "DROP": (self.handleDrop, False, "Unregister a channel that you registered",
                     "USAGE: \x02DROP channel\n"
                     "Unregister the given channel, so it will no longer be restored by chanserv. "
                     "Only the channel founder may do this."),
            "PROMOTE": (self.handlePromote, False, "Regain op status for a channel you registered",
                        "USAGE: \x02PROMOTE channel\n"
                        "Allows the founder (the person who registered the given channel) "
                        "to regain op status if they accidentially lock themselves out of it."),
        }

    def actions(self):
        return super(ChanServ, self).actions() + [
            ("channelcreate", 10, lambda channel, user: self.restoreChannel(channel)),
            ("topic", 10, lambda channel, setter, oldTopic: self.saveTopic(channel)),
            ("modechanges-channel", 10, lambda channel, source, sourceName, changing: self.saveModes(channel)),
            ("channelstatusoverride", 10, self.checkOverridePermission)
        ]
        # TODO may need to restore mode on new mode being registered (if we have that mode saved)

    def getStore(self):
        if "chanserv" not in self.ircd.storage:
            self.ircd.storage["chanserv"] = {}
        return self.ircd.storage["chanserv"]

    def checkOverridePermission(self, channel, user, mode, param):
        if user == self.user:
            return True
        return None

    def handleRegister(self, user, params):
        if not params:
            self.tellUser(user, "USAGE: \x02REGISTER channel")
            return

        channelName = params[0]
        if len(channelName) > 64 or not channelName.startswith("#"):
            self.tellUser(user, "{} is not a valid channel.".format(channelName))
            return

        donorID = getDonorID(user)
        if not donorID:
            self.tellUser(user, "You cannot register {}: You aren't logged in.".format(channelName))
            return

        if channelName not in self.ircd.channels:
            self.tellUser(user, "Channel {} does not exist.".format(channelName))
            return
        channel = self.ircd.channels[channelName]

        if channel.userRank(user) < 100 and not self.isAdmin(user):
            self.tellUser(user, "Only a channel op (or better) can register a channel.")
            return

        channels = self.getStore()
        if ircLower(channelName) in channels:
            self.tellUser(user, "Channel {} is already registered.".format(channelName))
            return

        # TODO set extban for +o for founder
        channels[ircLower(channelName)] = {
            "name": channelName,
            "founder": donorID,
            "existedSince": channel.existedSince,
        }
        self.saveTopic(channel)
        self.saveModes(channel)

        self.tellUser(user, "Channel {} has been registered.".format(channelName))

    def restoreChannel(self, channel):
        info = self.getStore().get(ircLower(channel.name), None)
        if not info:
            return

        channel.existedSince = info["existedSince"]

        # we manually set topic as there's no way to specify setter as a string, not a currently-logged-in user
        # or to set the setting time as any time but now.
        oldTopic = channel.topic
        channel.topic, channel.topicSetter, channel.topicTime = info["topic"]
        self.ircd.runActionStandard("topic", channel, self.ircd.serverID, oldTopic, channels=[channel])

        # restore modes
        modes = [mode for mode in info["modes"] if mode in self.ircd.channelModeTypes]
        self.restoreModes(channel, modes)

    def restoreModes(self, channel, modes):
        changes = []
        info = self.getStore()[ircLower(channel.name)]
        for mode in modes:
            modeType = self.ircd.channelModeTypes[mode]
            value = info["modes"][mode]
            if modeType == ModeType.List:
                for param, sourceName, time in value:
                    changes.append((mode, param))
            else:
                changes.append((mode, value))
        for n in range(0, len(changes), 20):
            # we need to split into lots of 20 changes, since this is the max setMode allows per call
            sublist = changes[n:n+20]
            modestr = ''.join([mode for mode, param in sublist])
            params = [param for mode, param in sublist if param is not None]
            channel.setModes(self.user.uuid, modestr, params)

    def saveTopic(self, channel):
        info = self.getStore().get(ircLower(channel.name), None)
        if not info:
            return
        info["topic"] = channel.topic, channel.topicSetter, channel.topicTime

    def saveModes(self, channel):
        info = self.getStore().get(ircLower(channel.name), None)
        if not info:
            return
        info["modes"] = channel.modes

    def handleDrop(self, user, params):
        if not params:
            self.tellUser(user, "USAGE: \x02DROP channel")
            return
        channelName = ircLower(params[0])
        donorID = getDonorID(user)
        if not donorID:
            self.tellUser(user, "Could not drop channel: You aren't logged in.")
            return
        channels = self.getStore()
        if channelName not in channels:
            self.tellUser(user, "Could not drop channel: No such channel {} is registered.".format(channelName))
            return
        if donorID != channels[channelName]["founder"] and not self.isAdmin(user):
            self.tellUser(user, "Only the channel founder can drop the channel.")
            return
        del channels[channelName]
        self.tellUser(user, "Successfully dropped channel {}".format(channelName))

    def handlePromote(self, user, params):
        if not params:
            self.tellUser(user, "USAGE: \x02PROMOTE channel")
            return
        channelName = ircLower(params[0])
        donorID = getDonorID(user)
        if not donorID:
            self.tellUser(user, "Cannot promote: You aren't logged in.")
            return
        channels = self.getStore()
        if channelName not in channels:
            self.tellUser(user, "Cannot promote: No such channel {} is registered.".format(channelName))
            return
        if donorID != channels[channelName]["founder"] and not self.isAdmin(user):
            self.tellUser(user, "Only the channel founder can promote themselves.")
            return
        if channelName not in self.ircd.channels:
            self.tellUser(user, "Your channel {} does not exist yet. Try JOINing it first.".format(channelName))
        channel = self.ircd.channels[channelName]
        channel.setModes(self.user.uuid, self.ircd.channelStatusOrder[0], [user.nick])


chanServ = ChanServ()
