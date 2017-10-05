from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class ServerChgGecos(ModuleData, Command):
	name = "ServerChangeGecos"
	core = True
	burstQueuePriority = 10
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("changegecos", 10, self.propagateGecosChange),
		         ("remotechangegecos", 10, self.propagateGecosChange) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("CHGGECOS", 1, self) ]
	
	def propagateGecosChange(self, user: "IRCUser", oldGecos: str, fromServer: "IRCServer" = None) -> None:
		self.ircd.broadcastToServers(fromServer, "CHGGECOS", user.uuid, user.gecos, prefix=self.ircd.serverID)
	
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
			"gecos": params[1]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostuser" not in data:
			data["user"].changeGecos(data["gecos"], server)
		return True

chgGecos = ServerChgGecos()