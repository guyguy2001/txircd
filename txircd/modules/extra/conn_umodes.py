from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
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
			user.setModes(self.ircd.serverID, modes, params)
		except KeyError:
			pass # No umodes defined. No action required.

autoUserModes = AutoUserModes()