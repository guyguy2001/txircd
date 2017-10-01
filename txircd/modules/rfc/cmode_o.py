from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer

@implementer(IPlugin, IModuleData, IMode)
class OpMode(ModuleData, Mode):
	name = "ChanopMode"
	core = True
	
	def channelModes(self):
		return [ ("o", ModeType.Status, self, 100, "@") ]
	
	def checkSet(self, chanel, param):
		return param.split(",")
	
	def checkUnset(self, channel, param):
		return param.split(",")

opMode = OpMode()