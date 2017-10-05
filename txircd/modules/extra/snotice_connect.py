from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Tuple

@implementer(IPlugin, IModuleData)
class SnoConnect(ModuleData):
	name = "ServerNoticeConnect"

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("register", 1, self.sendConnectNotice),
		         ("servernoticetype", 1, self.checkSnoType)]

	def sendConnectNotice(self, user: "IRCUser") -> bool:
		self.ircd.runActionStandard("sendservernotice", "connect", "Client connected on {}: {} ({}) [{}]".format(self.ircd.name, user.hostmaskWithRealHost(), user.ip, user.gecos))
		return True

	def checkSnoType(self, user: "IRCUser", typename: str) -> bool:
		return typename == "connect"

snoConnect = SnoConnect()