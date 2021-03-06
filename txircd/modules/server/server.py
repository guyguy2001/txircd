from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.server import RemoteServer
from zope.interface import implements

class ServerCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerCommand"
	core = True
	forRegistered = None
	
	def actions(self):
		return [ ("initiateserverconnection", 1, self.introduceSelf),
		         ("serverconnect", 10, self.propagateServer) ]
	
	def serverCommands(self):
		return [ ("SERVER", 1, self) ]
	
	def introduceSelf(self, server):
		server.sendMessage("SERVER", self.ircd.name, self.ircd.serverID, "0", self.ircd.serverID, self.ircd.config["server_description"], prefix=self.ircd.serverID)
	
	def propagateServer(self, server):
		hopCount = 1
		closestServer = server
		while closestServer.nextClosest != self.ircd.serverID:
			hopCount += 1
			closestServer = self.ircd.servers[closestServer.nextClosest]
		self.ircd.broadcastToServers(closestServer, "SERVER", server.name, server.serverID, str(hopCount), server.nextClosest, server.description, prefix=server.nextClosest)
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 5:
			return None
		return {
			"name": params[0],
			"id": params[1],
			"hops": params[2],
			"nextclosest": params[3],
			"description": params[4]
		}
	
	def execute(self, server, data):
		serverID = data["id"]
		if serverID in self.ircd.servers or serverID == self.ircd.serverID:
			server.disconnect("Server {} already exists".format(serverID))
			return True
		name = data["name"]
		if name in self.ircd.serverNames:
			server.disconnect("Server with name {} already exists".format(name))
			return True
		hopCount = int(data["hops"])
		if hopCount == 0:
			nextClosest = self.ircd.serverID
		else:
			nextClosest = data["nextclosest"]
			if nextClosest not in self.ircd.servers:
				server.disconnect("Next closest server {} does not exist".format(nextClosest))
				return True
		if hopCount == 0:
			newServer = server
		else:
			newServer = RemoteServer(self.ircd, "0.0.0.0")
		newServer.serverID = serverID
		newServer.name = name
		newServer.description = data["description"]
		newServer.nextClosest = nextClosest
		if hopCount == 0: # The connecting server is the server being introduced, so let's start the connection going
			if server.receivedConnection:
				server.sendMessage("SERVER", self.ircd.name, self.ircd.serverID, "0", server.serverID, self.ircd.config["server_description"], prefix=self.ircd.serverID)
				return True
			linkData = self.ircd.config.get("links", {})
			if server.name not in linkData:
				server.disconnect("No link block for server {}".format(server.name))
				return True
			if "out_password" in linkData[server.name]:
				password = linkData[server.name]["out_password"]
			else:
				password = ""
			server.sendMessage("PASS", password, prefix=self.ircd.serverID)
			return True
		newServer.register()
		return True

serverCmd = ServerCommand()