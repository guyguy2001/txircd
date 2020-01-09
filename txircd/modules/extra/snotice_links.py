from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Tuple

@implementer(IPlugin, IModuleData)
class SnoLinks(ModuleData):
	name = "ServerNoticeLinks"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("serverconnect", 1, self.announceConnect),
		         ("serverquit", 1, self.announceQuit),
		         ("servernoticetype", 1, self.checkSnoType) ]
	
	def announceConnect(self, server: "IRCServer") -> None:
		message = "Server {} ({}) connected (to {})".format(server.name, server.serverID, self.ircd.name if server.nextClosest == self.ircd.serverID else self.ircd.servers[server.nextClosest].name)
		self.ircd.runActionStandard("sendservernotice", "links", message)
	
	def announceQuit(self, server: "IRCServer", reason: str) -> None:
		if server.serverID:
			message = "Server {} ({}) disconnected (from {}) ({})".format(server.name, server.serverID, self.ircd.name if server.nextClosest == self.ircd.serverID else self.ircd.servers[server.nextClosest].name, reason)
		else:
			message = "Unregistered server at {} disconnected (from {}) ({})".format(server.ip, self.ircd.name if server.nextClosest == self.ircd.serverID else self.ircd.servers[server.nextClosest].name, reason)
		self.ircd.runActionStandard("sendservernotice", "links", message)
	
	def checkSnoType(self, user: "IRCUser", typename: str) -> bool:
		if typename == "links":
			return True
		return False

snoLinks = SnoLinks()