from twisted.plugin import IPlugin
from twisted.python import log
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements
import logging, re

irc.RPL_BADWORDADDED = "927"
irc.RPL_BADWORDREMOVED = "928"
irc.ERR_NOSUCHBADWORD = "929"

class Censor(ModuleData):
    implements(IPlugin, IModuleData)

    name = "Censor"
    exemptLevel = 100
    badwords = None

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def userCommands(self):
        return [ ("CENSOR", 1, CensorCommand(self)) ]

    def channelModes(self):
        return [ ("G", ModeType.NoParam, ChannelCensor(self)) ]

    def userModes(self):
        return [ ("G", ModeType.NoParam, UserCensor(self)) ]

    def actions(self):
        return [ ("modeactioncheck-channel-G-commandmodify-PRIVMSG", 10, self.channelHasMode),
                ("modeactioncheck-channel-G-commandmodify-NOTICE", 10, self.channelHasMode),
                ("modeactioncheck-user-G-commandmodify-PRIVMSG", 10, self.userHasMode),
                ("modeactioncheck-user-G-commandmodify-PRIVMSG", 10, self.userHasMode),
                ("commandpermission-CENSOR", 1, self.restrictToOpers),
                ("statstypename", 1, self.checkStatsType),
                ("statsruntype", 1, self.listStats) ]

    def restrictToOpers(self, user, command, data):
        if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-censor", users=[user]):
            user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
            return False
        return None

    def channelHasMode(self, channel, user, command, data):
        if "G" in channel.modes:
            return True
        return None

    def userHasMode(self, user, fromUser, *params):
        if "G" in user.modes:
            return True
        return None

    def checkStatsType(self, typeName):
        if typeName == "C":
            return "CENSOR"
        return None

    def listStats(self, user, typeName):
        if typeName == "CENSOR":
            return self.badwords
        return None

    def load(self):
        if "badwords" not in self.ircd.storage:
            self.ircd.storage["badwords"] = {}
        self.badwords = self.ircd.storage["badwords"]
        self.rehash()

    def fullUnload(self):
        for channel in self.ircd.channels.itervalues():
            if "G" in channel.modes:
                channel.setModes(self.ircd.serverID, "-G", [])

    def rehash(self):
        newLevel = self.ircd.config.getWithDefault("exempt_chanops_censor", 100)
        try:
            self.exemptLevel = int(newLevel)
        except ValueError:
            try:
                self.exemptLevel = self.ircd.channelStatuses[newLevel[0]][1]
            except KeyError:
                log.msg("Censor: No valid exempt level found; defaulting to 100", logLevel=logging.WARNING)
                self.exemptLevel = 100

class ChannelCensor(Mode):
    implements(IMode)

    affectedActions = [ "commandmodify-PRIVMSG", "commandmodify-NOTICE" ]

    def __init__(self, censor):
        self.censor = censor

    def apply(self, actionName, channel, param, user, command, data):
        if channel.userRank(user) < self.censor.exemptLevel and channel in data["targetchans"]:
            message = data["targetchans"][channel]
            for mask, replacement in self.censor.badwords.iteritems():
                message = re.sub(mask, replacement, message, flags=re.IGNORECASE)
            data["targetchans"][channel] = message

class UserCensor(Mode):
    implements(IMode)

    affectedActions = [ "commandmodify-PRIVMSG", "commandmodify-NOTICE" ]

    def __init__(self, censor):
        self.censor = censor

    def apply(self, actionName, targetUser, param, user, command, data):
        if "targetusers" not in data: # This can apparently trigger if a user with +G set on themselves sends a channel message
            return
        if targetUser in data["targetusers"]: 
            message = data["targetusers"][targetUser]
            for mask, replacement in self.censor.badwords.iteritems():
                message = re.sub(mask, replacement, message, flags=re.IGNORECASE)
            data["targetusers"][targetUser] = message

class CensorCommand(Command):
    implements(ICommand)

    def __init__(self, censor):
        self.censor = censor

    def parseParams(self, user, params, prefix, tags):
        if not params or not params[0]:
            user.sendSingleError("CensorCmd", irc.ERR_NEEDMOREPARAMS, "CENSOR", ":Not enough parameters")
            return None
        if len(params) == 1:
            # Removing a badword
            badword = params[0]
            if badword not in self.censor.badwords:
                user.sendSingleError("CensorCmd", irc.ERR_NOSUCHBADWORD, badword, ":No such badword")
                return None
            return {
                "badword": params[0]
            }
        else:
            # Adding a badword
            return {
                "badword": params[0],
                "replacement": params[1]
            }

    def execute(self, user, data):
        badword = data["badword"]
        if "replacement" in data:
            replacement = data["replacement"]
            self.censor.badwords[badword] = replacement
            self.censor.ircd.storage["badwords"] = self.censor.badwords
            user.sendMessage(irc.RPL_BADWORDADDED, badword, ":{}".format(replacement))
        else:
            del self.censor.badwords[badword]
            self.censor.ircd.storage["badwords"] = self.censor.badwords
            user.sendMessage(irc.RPL_BADWORDREMOVED, badword, ":Badword removed")
        return True

censorModule = Censor()