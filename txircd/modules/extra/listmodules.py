from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class ModulesCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ModulesCommand"
	
	def actions(self):
		return [ ("statsruntype-modules", 1, self.listModules) ]
	
	def listModules(self):
		return sorted(self.ircd.loadedModules.keys())

modulesCommand = ModulesCommand()