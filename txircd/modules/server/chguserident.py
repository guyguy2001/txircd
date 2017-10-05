from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class ServerChgIdent(ModuleData, Command):
	name = "ServerChangeIdent"
	core = True
	burstQueuePriority = 10
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("changeident", 10, self.propagateIdentChange),
		         ("remotechangeident", 10, self.propagateIdentChange) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("CHGIDENT", 1, self) ]
	
	def propagateIdentChange(self, user: "IRCUser", oldIdent: str, fromServer: "IRCServer" = None) -> None:
		self.ircd.broadcastToServers(fromServer, "CHGIDENT", user.uuid, user.ident, prefix=self.ircd.serverID)
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
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
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostuser" not in data:
			data["user"].changeIdent(data["ident"], server)
		return True

chgIdent = ServerChgIdent()