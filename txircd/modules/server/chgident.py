from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class ServerChgIdent(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerChangeIdent"
	core = True
	
	def actions(self):
		return [ ("changeident", 10, self.propagateIdentChange),
				("remotechangeident", 10, self.propagateIdentChange) ]
	
	def serverCommands(self):
		return [ ("CHGIDENT", 1, self) ]
	
	def propagateIdentChange(self, user, oldIdent, fromServer = None):
		for server in self.ircd.servers.itervalues():
			if server.nextClosest == self.ircd.serverID and server != fromServer:
				server.sendMessage("CHGIDENT", user.uuid, user.ident, prefix=self.ircd.serverID)
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		if params[0] not in self.ircd.users:
			return None
		return {
			"user": self.ircd.users[params[0]],
			"ident": params[1]
		}
	
	def execute(self, server, data):
		data["user"].changeIdent(data["ident"], server)
		return True

chgIdent = ServerChgIdent()