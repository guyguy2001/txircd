from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class ServerTime(ModuleData):
	name = "ServerTime"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("capabilitylist", 1, self.addCapability) ]
	
	def load(self) -> None:
		if "unloading-server-time" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-server-time"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("server-time")
	
	def unload(self) -> Optional["Deferred"]:
		self.ircd.dataCache["unloading-server-time"] = True
	
	def fullUnload(self) -> Optional["Deferred"]:
		del self.ircd.dataCache["unloading-server-time"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("server-time")
	
	def addCapability(self, user: "IRCUser", capList: List[str]) -> None:
		capList.append("server-time")

serverTime = ServerTime()