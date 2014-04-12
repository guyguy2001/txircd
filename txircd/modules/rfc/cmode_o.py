from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class OpMode(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "ChanopMode"
    core = True
    
    def channelModes(self):
        return [ ("o", ModeType.Status, self, 100, "@") ]

opMode = OpMode()