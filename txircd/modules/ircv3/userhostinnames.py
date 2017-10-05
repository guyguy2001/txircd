from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class UserhostInNames(ModuleData):
	name = "UserhostInNames"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("capabilitylist", 10, self.addCapability),
		         ("displaychanneluser", 10, self.showUserHostmask) ]
	
	def load(self) -> None:
		if "unloading-userhost-in-names" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-userhost-in-names"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("userhost-in-names")
	
	def unload(self) -> Optional["Deferred"]:
		self.ircd.dataCache["unloading-userhost-in-names"] = True
	
	def fullUnload(self) -> Optional["Deferred"]:
		del self.ircd.dataCache["unloading-userhost-in-names"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("userhost-in-names")
	
	def addCapability(self, user: "IRCUser", capList: List[str]) -> None:
		capList.append("userhost-in-names")
	
	def showUserHostmask(self, channel: "IRCChannel", showToUser: "IRCUser", showingUser: "IRCUser") -> Optional[str]:
		if "capabilities" not in showToUser.cache or "userhost-in-names" not in showToUser.cache["capabilities"]:
			return None
		return showingUser.hostmask()

uhNames = UserhostInNames()