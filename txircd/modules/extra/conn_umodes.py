from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class AutoUserModes(ModuleData):
	implements(IPlugin, IModuleData)

	name = "AutoUserModes"

	def actions(self):
		return [ ("welcome", 50, self.autoSetUserModes) ]

	def autoSetUserModes(self, user):
		try:
			modes = self.ircd.config["client_umodes_on_connect"]
			params = modes.split()
			modes = params.pop(0)
			parsedModes = []
			for mode in modes:
				if mode not in self.ircd.userModeTypes:
					continue
				modeType = self.ircd.userModeTypes[mode]
				if modeType in (ModeType.List, ModeType.ParamOnUnset, ModeType.Param):
					parsedModes.append((True, mode, params.pop(0)))
				else:
					parsedModes.append((True, mode, None))
			user.setModes(parsedModes, self.ircd.serverID)
		except KeyError:
			pass # No umodes defined. No action required.

autoUserModes = AutoUserModes()