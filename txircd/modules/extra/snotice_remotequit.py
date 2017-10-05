from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class SnoRemoteQuit(ModuleData):
	name = "ServerNoticeRemoteQuit"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("remotequit", 1, self.sendRemoteQuitNotice),
		         ("servernoticetype", 1, self.checkSnoType) ]
	
	def sendRemoteQuitNotice(self, user: "IRCUser", reason: str, fromServer: Optional["IRCServer"]) -> None:
		server = self.ircd.servers[user.uuid[:3]]
		if not server.bursted: # Server is disconnecting
			return
		self.ircd.runActionStandard("sendservernotice", "remotequit", "Client quit from {}: {} ({}) [{}]".format(server.name, user.hostmaskWithRealHost(), user.ip, reason))
	
	def checkSnoType(self, user: "IRCUser", typename: str) -> bool:
		return typename == "remotequit"

snoRemoteQuit = SnoRemoteQuit()