from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class ModulesList(ModuleData):
	name = "ModulesList"
	
	def actions(self):
		return [ ("statsruntype-modules", 1, self.listModules) ]
	
	def listModules(self):
		modules = {}
		for modName in self.ircd.loadedModules.keys():
			modules[modName] = "*"
		return modules

modulesList = ModulesList()