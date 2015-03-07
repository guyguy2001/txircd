from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class DellineCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "ServerDelline"
	core = True

	def actions(self):
		return [ ("propagateremovexline", 1, self.propagateRemoveXLine) ]

	def serverCommands(self):
		return [ ("DELLINE", 10, self) ]

	def propagateRemoveXLine(self, linetype, mask):
		self.ircd.broadcastToServers(None, "DELLINE", linetype, mask, prefix=self.ircd.serverID)

	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		return {
			"linetype": params[0],
			"mask": params[1]
		}

	def execute(self, server, data):
		lineType = data["linetype"]
		mask = data["mask"]
		self.ircd.runActionStandard("removexline", lineType, mask)
		self.ircd.broadcastToServers(server, "DELLINE", lineType, mask, prefix=self.ircd.serverID)cd.serverID)
		return True

dellineCmd = DellineCommand()