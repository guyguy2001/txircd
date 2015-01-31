from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class ServerChgHost(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerChangeHost"
	core = True
	
	def hookIRCd(self, ircd):
		self.ircd = ircd
	
	def actions(self):
		return [ ("changehost", 10, self.propagateChangeHost),
				("remotechangehost", 10, self.propagateChangeHost) ]
	
	def serverCommands(self):
		return [ ("CHGHOST", 1, self) ]
	
	def propagateChangeHost(self, user, oldHost, fromServer = None):
		for server in self.ircd.servers.itervalues():
			if server.nextClosest == self.ircd.serverID and server != fromServer:
				server.sendMessage("CHGHOST", user.uuid, user.host, prefix=self.ircd.serverID)
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		if params[0] not in self.ircd.users:
			return None
		return {
			"user": self.ircd.users[params[0]],
			"host": params[1]
		}
	
	def execute(self, server, data):
		data["user"].changeHost(data["host"], server)
		return True

chgHost = ServerChgHost()