from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class ChangeHost(ModuleData):
	name = "ChangeHost"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("changehost", 1, self.updateHosts),
		         ("changeident", 1, self.updateIdents),
		         ("remotechangeident", 1, self.updateIdents),
		         ("capabilitylist", 1, self.addCapability) ]
	
	def load(self) -> None:
		if "unloading-chghost" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-chghost"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("chghost")
	
	def unload(self) -> Optional["Deferred"]:
		self.ircd.dataCache["unloading-chghost"] = True
	
	def fullUnload(self) -> Optional["Deferred"]:
		del self.ircd.dataCache["unloading-chghost"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("chghost")
	
	def addCapability(self, user: "IRCUser", capList: List[str]) -> None:
		capList.append("chghost")
	
	def updateHosts(self, user: "IRCUser", hostType: str, oldHost: str, fromServer: Optional["IRCServer"]) -> None:
		userIdent = user.ident
		userHost = user.host()
		userPrefix = "{}!{}@{}".format(user.nick, userIdent, oldHost)
		self.sendToChannelUsers(user, userIdent, userHost, userPrefix)
	
	def updateIdents(self, user: "IRCUser", oldIdent: str, fromServer: Optional["IRCServer"]) -> None:
		userIdent = user.ident
		userHost = user.host()
		userPrefix = "{}!{}@{}".format(user.nick, oldIdent, userHost)
		self.sendToChannelUsers(user, userIdent, userHost, userPrefix)
	
	def sendToChannelUsers(self, user: "IRCUser", userIdent: str, userHost: str, userPrefix: str) -> None:
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		channelUsers = set()
		for channel in user.channels:
			for chanUser in channel.users.keys():
				channelUsers.add(chanUser)
		for chanUser in channelUsers:
			if "capabilities" not in chanUser.cache or "chghost" not in chanUser.cache["capabilities"]:
				continue
			tags = chanUser.filterConditionalTags(conditionalTags)
			chanUser.sendMessage("CHGHOST", userIdent, userHost, to=None, prefix=userPrefix, tags=tags)

changeHost = ChangeHost()