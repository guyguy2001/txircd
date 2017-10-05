from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ircLower
from zope.interface import implementer
from fnmatch import fnmatchcase
from typing import Callable, List, Tuple

@implementer(IPlugin, IModuleData)
class AccountExtban(ModuleData):
	name = "AccountExtban"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("usermatchban-R", 1, self.matchBan),
		  ("usermetadataupdate", 10, self.updateBansOnAccountChange) ]
	
	def matchBan(self, user: "IRCUser", matchNegated: bool, mask: str) -> bool:
		if not user.metadataKeyExists("account"):
			return matchNegated
		userAccount = ircLower(user.metadataValue("account"))
		lowerMask = ircLower(mask)
		if fnmatchcase(userAccount, lowerMask):
			return not matchNegated
		return matchNegated
	
	def updateBansOnAccountChange(self, user: "IRCUser", key: str, oldValue: str, value: str, fromServer: "IRCServer" = None) -> None:
		if key != "account":
			return
		self.ircd.runActionStandard("updateuserbancache", user)

matchExtban = AccountExtban()