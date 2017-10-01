from twisted.plugin import IPlugin
from txircd.factory import UserFactory
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class StatsPorts(ModuleData):
	name = "StatsPorts"

	def actions(self):
		return [ ("statsruntype-ports", 10, self.listPorts) ]

	def listPorts(self):
		info = {}
		for portDesc, portData in self.ircd.boundPorts.items():
			if isinstance(portData.factory, UserFactory):
				info[str(portData.port)] = "{} (clients)".format(portDesc)
			else:
				info[str(portData.port)] = "{} (servers)".format(portDesc)
		return info

statsPorts = StatsPorts()