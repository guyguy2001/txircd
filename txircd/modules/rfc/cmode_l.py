from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class LimitMode(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "LimitMode"
    core = True
    affectedActions = [ "joinpermission" ]
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def channelModes(self):
        return [ ("l", ModeType.Param, self) ]
    
    def actions(self):
        return [ ("modeactioncheck-channel-l-joinpermission", 10, self.isModeSet) ]
    
    def isModeSet(self, channel, alsoChannel, user):
        if "l" in channel.modes:
            return channel.modes["l"]
        return None
    
    def checkSet(self, channel, param):
        try:
            return [ int(param) ]
        except ValueError:
            return None
    
    def apply(self, actionType, channel, param, alsoChannel, user):
        if len(channel.users) >= param:
            user.sendMessage(irc.ERR_CHANNELISFULL, channel.name, ":Cannot join channel (Channel is full)")
            return False
        return None

limitMode = LimitMode()