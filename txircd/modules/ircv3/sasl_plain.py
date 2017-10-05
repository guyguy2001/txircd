from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from base64 import b64decode
from typing import Callable, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData)
class SASLPlain(ModuleData):
	name = "SASLPlain"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("saslmechanismlist", 10, self.addPlainToMechList),
			("startsasl", 10, self.acceptPlain),
			("authenticatesasl", 10, self.startAuth) ]
	
	def load(self) -> None:
		if "unloading-sasl-plain" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-sasl-plain"]
			return
		if "saslmech-add" in self.ircd.functionCache:
			self.ircd.functionCache["saslmech-add"]("PLAIN")
	
	def unload(self) -> Optional["Deferred"]:
		self.ircd.dataCache["unloading-sasl-plain"] = True
	
	def fullUnload(self) -> Optional["Deferred"]:
		del self.ircd.dataCache["unloading-sasl-plain"]
		if "saslmech-del" in self.ircd.functionCache:
			self.ircd.functionCache["saslmech-del"]("PLAIN")
	
	def addPlainToMechList(self, mechList: List[str]) -> None:
		mechList.append("PLAIN")
	
	def acceptPlain(self, user: "IRCUser", mechanism: str) -> bool:
		if mechanism == "PLAIN":
			user.sendMessage("AUTHENTICATE", "+", prefix=None, to=None)
			return True
		return False
	
	def startAuth(self, user: "IRCUser", saslData: bytes) -> Union[str, bool]:
		if "sasl-mech" not in user.cache or user.cache["sasl-mech"] != "PLAIN":
			return None
		plainData = b64decode(saslData)
		try:
			username, _, password = plainData.split("\0")
		except ValueError:
			return False
		result = self.ircd.runActionUntilValue("authenticatesasl-PLAIN", user, username, password)
		if result is None:
			return False
		return result

plainSASLAuth = SASLPlain()