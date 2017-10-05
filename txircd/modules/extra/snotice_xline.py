from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Tuple

@implementer(IPlugin, IModuleData)
class SnoXLine(ModuleData):
	name = "ServerNoticeXLine"

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("addxline", 1, self.announceAdd),
		         ("delxline", 1, self.announceRemove),
		         ("servernoticetype", 1, self.checkSnoType) ]

	def announceAdd(self, lineType: str, mask: str, duration: int, setter: str, reason: str) -> None:
		message = "{} added {} x:line of type {} for {}{} ({})".format(setter, "permanent" if duration == 0 else "timed", lineType, mask, ", to expire in {} seconds".format(duration) if duration > 0 else "", reason)
		self.ircd.runActionStandard("sendservernotice", "xline", message)

	def announceRemove(self, lineType: str, mask: str, setter: str) -> None:
		message = "{} removed x:line of type {} for {}".format(setter, lineType, mask)
		self.ircd.runActionStandard("sendservernotice", "xline", message)

	def checkSnoType(self, user: "IRCUser", typename: str) -> bool:
		return typename == "xline"

snoXline = SnoXLine()