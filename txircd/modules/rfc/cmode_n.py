from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class NoExtMsgMode(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "NoExtMsgMode"
    core = True
    affectedActions = [ "commandpermission-PRIVMSG", "commandpermission-NOTICE" ]
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def channelModes(self):
        return [ ("n", ModeType.NoParam, self) ]
    
    def actions(self):
        return [ ("modeactioncheck-channel-n-commandpermission-PRIVMSG", 1, self.channelHasMode),
                ("modeactioncheck-channel-n-commandpermission-NOTICE", 1, self.channelHasMode) ]
    
    def apply(self, actionType, channel, param, user, command, data):
        if user not in channel.users:
            user.startCommandErrorBatch("CMode-n")
            user.sendCommandError("CMode-n", irc.ERR_CANNOTSENDTOCHAN, channel.name, ":Cannot send to channel (no external messages)")
            return False
        return None
    
    def channelHasMode(self, channel, user, command, data):
        if "n" in channel.modes:
            return ""
        return None

noExtMsgMode = NoExtMsgMode()