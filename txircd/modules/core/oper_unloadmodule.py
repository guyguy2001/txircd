from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

# We're using the InspIRCd numerics, as they seem to be the only ones to actually use numerics
irc.ERR_CANTUNLOADMODULE = "972"
irc.RPL_UNLOADEDMODULE = "973"

class UnloadModuleCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "UnloadModuleCommand"
	core = True

	def actions(self):
		return [ ("commandpermission-UNLOADMODULE", 1, self.restrictToOpers) ]

	def userCommands(self):
		return [ ("UNLOADMODULE", 1, self) ]

	def restrictToOpers(self, user, command, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-unloadmodule", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendSingleError("UnloadModuleCmd", irc.ERR_NEEDMOREPARAMS, "UNLOADMODULE", "Not enough parameters")
			return None
		return {
			"modulename": params[0]
		}

	def execute(self, user, data):
		moduleName = data["modulename"]
		if moduleName not in self.ircd.loadedModules:
			user.sendMessage(irc.ERR_CANTUNLOADMODULE, moduleName, "No such module")
		else:
			try:
				self.ircd.unloadModule(moduleName)
				user.sendMessage(irc.RPL_UNLOADEDMODULE, moduleName, "Module successfully unloaded")
			except ValueError as e:
				user.sendMessage(irc.ERR_CANTUNLOADMODULE, moduleName, e.message)
		return True

unloadmoduleCommand = UnloadModuleCommand()