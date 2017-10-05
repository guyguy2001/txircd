from twisted.plugin import IPlugin
from txircd import protoVersion
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class PassCommand(ModuleData, Command):
	name = "ServerPassCommand"
	core = True
	forRegistered = False
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("PASS", 1, self) ]
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 1:
			return None
		return {
			"password": params[0]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if not server.name:
			return False
		serverLinks = self.ircd.config.get("links", {})
		if server.name not in serverLinks:
			return False
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