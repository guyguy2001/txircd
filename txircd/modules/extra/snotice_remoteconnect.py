from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Tuple

@implementer(IPlugin, IModuleData)
class SnoRemoteConnect(ModuleData):
	name = "ServerNoticeRemoteConnect"
	
	def __init__(self):
		self.burstingServer = None
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("remoteregister", 1, self.sendRemoteConnectNotice),
		         ("servernoticetype", 1, self.checkSnoType),
		         ("startburstcommand", 1, self.markStartBurst),
		         ("endburstcommand", 1, self.markEndBurst) ]
	
	def sendRemoteConnectNotice(self, user: "IRCUser") -> None:
		server = self.ircd.servers[user.uuid[:3]]
		if server == self.burstingServer:
			return
		self.ircd.runActionStandard("sendservernotice", "remoteconnect", "Client connected on {}: {} ({}) [{}]".format(server.name, user.hostmaskWithRealHost(), user.ip.compressed, user.gecos))
	
	def checkSnoType(self, user: "IRCUser", typename: str) -> bool:
		return typename == "remoteconnect"
	
	def markStartBurst(self, server: "IRCServer", command: str) -> None:
		self.burstingServer = server
	
	def markEndBurst(self, server: "IRCServer", command: str) -> None:
		self.burstingServer = None

snoRemoteConnect = SnoRemoteConnect()