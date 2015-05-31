from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class DefaultModes(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "DefaultModes"
	core = True
	
	def actions(self):
		return [ ("channelcreate", 110, self.setDefaults) ]

	def verifyConfig(self, config):
		if "channel_default_modes" in config and not isinstance("channel_default_modes", basestring):
			raise ConfigValidationError("channel_default_modes", "value must be a string of mode letters")
	
	def setDefaults(self, channel, user):
		modes = self.ircd.config.get("channel_default_modes", "ont")
		params = modes.split(" ")
		modeList = list(params.pop(0))
		settingModes = []
		for mode in modeList:
			if mode not in self.ircd.channelModeTypes:
				continue
			modeType = self.ircd.channelModeTypes[mode]
			if modeType == ModeType.Status:
				settingModes.append((True, mode, user.uuid))
			elif modeType in (ModeType.List, ModeType.ParamOnUnset, ModeType.Param):
				settingModes.append((True, mode, params.pop(0)))
			else:
				settingModes.append((True, mode, None))
		channel.setModes(settingModes, self.ircd.serverID)

defaultModes = DefaultModes()