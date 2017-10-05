from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class AccountNotify(ModuleData):
	name = "AccountNotify"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("usermetadataupdate", 10, self.sendAccountNotice),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self) -> None:
		if "unloading-account-notify" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-account-notify"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("account-notify")
	
	def unload(self) -> Optional["Deferred"]:
		self.ircd.dataCache["unloading-account-notify"] = True
	
	def fullUnload(self) -> Optional["Deferred"]:
		del self.ircd.dataCache["unloading-account-notify"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("account-notify")
	
	def addCapability(self, user: "IRCUser", capList: List[str]) -> None:
		capList.append("account-notify")
	
	def sendAccountNotice(self, user: "IRCUser", key: str, oldValue: str, value: str, fromServer: Optional["IRCServer"]) -> None:
		if key != "account":
			return
		noticeUsers = set()
		noticePrefix = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		for channel in user.channels:
			for noticeUser in channel.users.keys():
				if noticeUser.uuid[:3] == self.ircd.serverID and noticeUser != user and "capabilities" in noticeUser.cache and "account-notify" in noticeUser.cache["capabilities"]:
					noticeUsers.add(noticeUser)
		if value:
			for noticeUser in noticeUsers:
				tags = noticeUser.filterConditionalTags(conditionalTags)
				noticeUser.sendMessage("ACCOUNT", value, to=None, prefix=noticePrefix, tags=tags)
		else:
			for noticeUser in noticeUsers:
				tags = noticeUser.filterConditionalTags(conditionalTags)
				noticeUser.sendMessage("ACCOUNT", "*", to=None, prefix=noticePrefix, tags=tags)

accountNotify = AccountNotify()