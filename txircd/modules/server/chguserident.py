from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData, ICommand)
class ServerChgIdent(ModuleData, Command):
	name = "ServerChangeIdent"
	core = True
	burstQueuePriority = 10
	
	def actions(self):
		return [ ("changeident", 10, self.propagateIdentChange),
		         ("remotechangeident", 10, self.propagateIdentChange) ]
	
	def serverCommands(self):
		return [ ("CHGIDENT", 1, self) ]
	
	def propagateIdentChange(self, user, oldIdent, fromServer = None):
		self.ircd.broadcastToServers(fromServer, "CHGIDENT", user.uuid, user.ident, prefix=self.ircd.serverID)
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		return {
			"user": self.ircd.users[params[0]],
			"ident": params[1]
		}
	
	def execute(self, server, data):
		if "lostuser" not in data:
			data["user"].changeIdent(data["ident"], server)
		return True

chgIdent = ServerChgIdent()