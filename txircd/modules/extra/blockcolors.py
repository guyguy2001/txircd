from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class BlockColors(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)

    name = "BlockColors"
    affectedActions = [ "commandmodify-PRIVMSG", "commandmodify-NOTICE" ]

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def channelModes(self):
        return [ ("c", ModeType.NoParam, self) ]

    def actions(self):
        return [ ("modeactioncheck-channel-c-commandmodify-PRIVMSG", 10, self.channelHasMode),
                ("modeactioncheck-channel-c-commandmodify-NOTICE", 10, self.channelHasMode) ]

    def channelHasMode(self, channel, user, command, data):
        if "c" in channel.modes:
            return ""
        return None

    def apply(self, actionName, channel, param, user, command, data):
        minAllowedRank = self.ircd.config.getWithDefault("exempt_chanops_blockcolor", 20)
        if channel.userRank(user) < minAllowedRank and channel in data["targetchans"]:
            message = data["targetchans"][channel]
            if any(c in message for c in "\x02\x1f\x16\x1d\x0f\x03"):
                del data["targetchans"][channel]
                user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, ":Cannot send colors to channel (+c)")

    def fullUnload(self):
        for channel in self.ircd.channels.itervalues():
            if "c" in channel.modes:
                channel.setModes(self.ircd.serverID, "-c", [])

blockColors = BlockColors()