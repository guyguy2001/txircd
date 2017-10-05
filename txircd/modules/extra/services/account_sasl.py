from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData)
class AccountSASL(ModuleData):
	name = "AccountSASL"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("authenticatesasl-PLAIN", 1, self.checkPlain) ]
	
	def checkPlain(self, user: "IRCUser", username: str, password: str) -> Union[str, bool]:
		resultValue = self.ircd.runActionUntilValue("accountauthenticate", user, username, password)
		if not resultValue:
			return False
		if resultValue[0] is None:
			resultValue[1].addCallback(self.completeSASL, user)
			return "defer"
		return resultValue[0]
	
	def completeSASL(self, result: Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]], user: "IRCUser") -> None:
		self.ircd.runActionStandard("saslcomplete", user, result[0])

accountSASL = AccountSASL()