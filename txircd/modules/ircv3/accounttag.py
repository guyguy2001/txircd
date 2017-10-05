from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class AccountTag(ModuleData):
	name = "AccountTag"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("sendingusertags", 1, self.addAccountTag),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self) -> None:
		if "unloading-account-tag" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-account-tag"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("account-tag")
	
	def unload(self) -> Optional["Deferred"]:
		self.ircd.dataCache["unloading-account-tag"] = True
	
	def fullUnload(self) -> Optional["Deferred"]:
		del self.ircd.dataCache["unloading-account-tag"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("account-tag")
	
	def addCapability(self, user: "IRCUser", capList: List[str]) -> None:
		capList.append("account-tag")
	
	def addAccountTag(self, fromUser: "IRCUser", conditionalTags: Dict[str, Tuple[str, Callable[["IRCUser"], bool]]]) -> None:
		if fromUser.metadataKeyExists("account"):
			conditionalTags["account"] = (fromUser.metadataValue("account"), lambda user: "capabilities" in user.cache and "account-tag" in user.cache["capabilities"])

accountTag = AccountTag()