from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Tuple

irc.RPL_WHOISACCOUNT = "330"

@implementer(IPlugin, IModuleData)
class WhoisAccount(ModuleData):
	name = "WhoisAccount"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("extrawhois", 1, self.whoisAccountName) ]
	
	def whoisAccountName(self, user: "IRCUser", targetUser: "IRCUser") -> None:
		if targetUser.metadataKeyExists("account"):
			user.sendMessage(irc.RPL_WHOISACCOUNT, targetUser.nick, targetUser.metadataValue("account"), "is logged in as")

whoisAccount = WhoisAccount()