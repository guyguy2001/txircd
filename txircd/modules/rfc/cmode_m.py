from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class ModeratedMode(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "ModeratedMode"
    core = True
    affectedActions = [ "commandmodify-PRIVMSG", "commandmodify-NOTICE" ]
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def channelModes(self):
        return [ ("m", ModeType.NoParam, self) ]
    
    def actions(self):
        return [ ("modeactioncheck-channel-m-commandmodify-PRIVMSG", 10, self.channelHasMode),
                ("modeactioncheck-channel-m-commandmodify-NOTICE", 10, self.channelHasMode) ]
    
    def channelHasMode(self, channel, user, command, data):
        if "m" in channel.modes:
            return ""
        return None
    
    def apply(self, actionName, channel, param, user, command, data):
        if channel.userRank(user) < 10 and channel in data["targetchans"]:
            data["targetchans"].remove(channel)
            user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, ":Cannot send to channel (+m)")

moderatedMode = ModeratedMode()