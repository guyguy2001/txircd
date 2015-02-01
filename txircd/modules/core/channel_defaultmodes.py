from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class DefaultModes(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "DefaultModes"
	core = True
	
	def actions(self):
		return [ ("channelcreate", 110, self.setDefaults) ]
	
	def setDefaults(self, channel, user):
		modes = self.ircd.config.get("channel_default_modes", "ont")
		statusModes = set()
		params = modes.split(" ")
		modeList = list(params.pop(0))
		for mode in modeList:
			if mode not in self.ircd.channelModeTypes:
				continue
			if self.ircd.channelModeTypes[mode] == ModeType.Status:
				statusModes.add(mode)
		for mode in statusModes:
			modeList.remove(mode)
		for mode in statusModes:
			modeList.append(mode)
			params.append(user.nick)
		channel.setModes(self.ircd.serverID, "".join(modeList), params)

defaultModes = DefaultModes()