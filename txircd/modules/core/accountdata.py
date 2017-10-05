from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple

# Numerics and names are taken from the IRCv3.1 SASL specification at http://ircv3.net/specs/extensions/sasl-3.1.html
irc.RPL_LOGGEDIN = "900"
irc.RPL_LOGGEDOUT = "901"

@implementer(IPlugin, IModuleData)
class AccountMetadata(ModuleData):
	name = "AccountData"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("usermetadataupdate", 10, self.sendLoginNumeric) ]
	
	def sendLoginNumeric(self, user: "IRCUser", key: str, oldValue: str, value: str, fromServer: Optional["IRCServer"]) -> None:
		if key == "account":
			if value is None:
				user.sendMessage(irc.RPL_LOGGEDOUT, user.hostmask(), "You are now logged out")
			else:
				user.sendMessage(irc.RPL_LOGGEDIN, user.hostmask(), value, "You are now logged in as {}".format(value))

accounts = AccountMetadata()
