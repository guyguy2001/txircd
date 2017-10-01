from twisted.plugin import IPlugin
from txircd import protoVersion
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData, ICommand)
class CapabCommand(ModuleData, Command):
	name = "CapabCommand"
	core = True
	forRegistered = False
	
	def serverCommands(self):
		return [ ("CAPAB", 1, self) ]
	
	def parseParams(self, server, params, prefix, tags):
		if not params:
			return None
		subcmd = params[0].upper()
		if subcmd == "START":
			if len(params) != 2:
				return None
			return {
				"subcmd": subcmd,
				"version": params[1]
			}
		if subcmd == "MODULES":
			if len(params) != 2:
				return None
			return {
				"subcmd": subcmd,
				"modules": params[1].split(" ")
			}
		if subcmd == "END":
			if len(params) != 1:
				return None
			return {
				"subcmd": subcmd
			}
		return None
	
	def execute(self, server, data):
		subcmd = data["subcmd"]
		if subcmd == "START":
			version = data["version"]
			if version != protoVersion:
				server.disconnect("Incompatible protocol version {}".format(version))
				return True
			return True
		if subcmd == "MODULES":
			moduleList = data["modules"]
			missingModules = self.ircd.commonModules.difference(moduleList)
			if missingModules:
				server.disconnect("Link Error: Not all required modules are loaded [Missing {}]".format(", ".join(missingModules)))
				return True
			return True
		if subcmd == "END":
			if server.serverID in self.ircd.servers:
				server.disconnect("Server {} already exists".format(server.serverID))
				return True
			if server.name in self.ircd.serverNames:
				server.disconnect("Server with name {} already exists".format(server.name))
				return True
			server.register()
			if server.receivedConnection:
				server.sendMessage("CAPAB", "START", protoVersion, prefix=self.ircd.serverID)
				server.sendMessage("CAPAB", "MODULES", " ".join(self.ircd.loadedModules.keys()), prefix=self.ircd.serverID)
				server.sendMessage("CAPAB", "END", prefix=self.ircd.serverID)
			self.ircd.runActionStandard("burst", server)
			return True
		return None

capabCmd = CapabCommand()