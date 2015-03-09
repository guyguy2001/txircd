from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class SecretMode(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "SecretMode"
	core = True
	affectedActions = { "displaychannel": 10 }
	
	def channelModes(self):
		return [ ("s", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-s-displaychannel", 1, self.chanIsSecret) ]
	
	def chanIsSecret(self, channel, displayData, sameChannel, user):
		if "s" in channel.modes:
			return True
		return None
	
	def apply(self, actionName, channel, param, displayData, sameChannel, user):
		if user not in channel.users:
			displayData.clear() # Let's make it not show the channel at all

secretMode = SecretMode()