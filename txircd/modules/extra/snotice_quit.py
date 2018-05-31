from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ipAddressToShow
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class SnoQuit(ModuleData):
	name = "ServerNoticeQuit"

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("quit", 1, self.sendQuitNotice),
		         ("servernoticetype", 1, self.checkSnoType)]

	def sendQuitNotice(self, user: "IRCUser", reason: str, fromServer: Optional["IRCServer"]) -> None:
		if not user.isRegistered():
			return
		self.ircd.runActionStandard("sendservernotice", "quit", "Client quit from {}: {} ({}) [{}]".format(self.ircd.name, user.hostmaskWithRealHost(), ipAddressToShow(user.ip), reason))

	def checkSnoType(self, user: "IRCUser", typename: str) -> bool:
		return typename == "quit"

snoQuit = SnoQuit()