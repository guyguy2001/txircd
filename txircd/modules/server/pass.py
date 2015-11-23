from twisted.plugin import IPlugin
from txircd import protoVersion
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class PassCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerPassCommand"
	core = True
	forRegistered = False
	
	def serverCommands(self):
		return [ ("PASS", 1, self) ]
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		return {
			"password": params[0]
		}
	
	def execute(self, server, data):
		if not server.name:
			return None
		serverLinks = self.ircd.config.get("links", {})
		if server.name not in serverLinks:
			return None
		receivedPassword = data["password"]
		checkPassword = serverLinks[server.name]["in_password"] if "in_password" in serverLinks[server.name] else ""
		if checkPassword == receivedPassword:
			server.cache["authenticated"] = True
			if server.receivedConnection:
				sendPassword = serverLinks[server.name]["out_password"] if "out_password" in serverLinks[server.name] else ""
				server.sendMessage("PASS", sendPassword, prefix=self.ircd.serverID)
			else:
				server.sendMessage("CAPAB", "START", protoVersion, prefix=self.ircd.serverID)
				server.sendMessage("CAPAB", "MODULES", " ".join(self.ircd.loadedModules.keys()), prefix=self.ircd.serverID)
				server.sendMessage("CAPAB", "END", prefix=self.ircd.serverID)
			return True
		server.disconnect("Incorrect password")
		return True

passCmd = PassCommand()