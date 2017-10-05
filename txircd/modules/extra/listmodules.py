from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, Dict, List, Tuple

@implementer(IPlugin, IModuleData)
class ModulesList(ModuleData):
	name = "ModulesList"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("statsruntype-modules", 1, self.listModules) ]
	
	def listModules(self) -> Dict[str, str]:
		modules = {}
		for modName in self.ircd.loadedModules.keys():
			modules[modName] = "*"
		return modules

modulesList = ModulesList()