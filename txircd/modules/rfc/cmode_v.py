from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class VoiceMode(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "ChanVoiceMode"
    core = True
    
    def channelModes(self):
        return [ ("v", ModeType.Status, self, 10, "+") ]
    
    def checkSet(self, channel, param):
        return param.split(",")

voiceMode = VoiceMode()