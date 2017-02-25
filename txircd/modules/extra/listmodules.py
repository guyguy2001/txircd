from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

# Using the RatBox numerics (and names) here, which most IRCds seem to use
irc.RPL_MODLIST = "702"
irc.RPL_ENDOFMODLIST = "703"

class ModulesCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ModulesCommand"
	
	def actions(self):
		return [ ("statsruntype-modules", 1, self.listModules) ]
	
	def listModules(self):
		return sorted(self.ircd.loadedModules.keys())

modulesCommand = ModulesCommand()