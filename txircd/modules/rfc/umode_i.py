from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class InvisibleMode(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "InvisibleMode"
    core = True
    affectedActions = [ "showchanneluser" ]
    
    def actions(self):
        return [ ("modeactioncheck-user-i-showchanneluser", 1, self.isInvisible) ]
    
    def userModes(self):
        return [ ("i", ModeType.NoParam, self) ]
    
    def isInvisible(self, user, channel, fromUser, userSeeing):
        if "i" in user.modes:
            return True
        return None
    
    def apply(self, actionName, user, param, channel, fromUser, sameUser):
        if user != sameUser:
            return None
        if not channel or fromUser not in channel.users:
            return False
        return None

invisibleMode = InvisibleMode()