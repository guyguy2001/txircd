from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData, ICommand)
class ServerChgGecos(ModuleData, Command):
	name = "ServerChangeGecos"
	core = True
	burstQueuePriority = 10
	
	def actions(self):
		return [ ("changegecos", 10, self.propagateGecosChange),
		         ("remotechangegecos", 10, self.propagateGecosChange) ]
	
	def serverCommands(self):
		return [ ("CHGGECOS", 1, self) ]
	
	def propagateGecosChange(self, user, oldGecos, fromServer = None):
		self.ircd.broadcastToServers(fromServer, "CHGGECOS", user.uuid, user.gecos, prefix=self.ircd.serverID)
	
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
			"gecos": params[1]
		}
	
	def execute(self, server, data):
		if "lostuser" not in data:
			data["user"].changeGecos(data["gecos"], server)
		return True

chgGecos = ServerChgGecos()