from twisted.plugin import IPlugin
from txircd.factory import UserFactory
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, Dict, List, Tuple

@implementer(IPlugin, IModuleData)
class StatsPorts(ModuleData):
	name = "StatsPorts"

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("statsruntype-ports", 10, self.listPorts) ]

	def listPorts(self) -> Dict[str, str]:
		info = {}
		for portDesc, portData in self.ircd.boundPorts.items():
			if isinstance(portData.factory, UserFactory):
				info[str(portData.port)] = "{} (clients)".format(portDesc)
			else:
				info[str(portData.port)] = "{} (servers)".format(portDesc)
		return info

statsPorts = StatsPorts()