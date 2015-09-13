from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class AccountTag(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountTag"
	
	def actions(self):
		return [ ("modifyoutgoingmessage", 1, self.addAccountTag),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self):
		if "unloading-account-tag" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-account-tag"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("account-tag")
	
	def unload(self):
		self.ircd.dataCache["unloading-account-tag"]
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-account-tag"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("account-tag")
	
	def addCapability(self, user, capList):
		capList.append("account-tag")
	
	def addAccountTag(self, user, command, args, kw):
		if "prefix" not in kw:
			return
		if "capabilities" not in user.cache or "account-tag" not in user.cache["capabilities"]:
			return
		prefix = kw["prefix"]
		if "!" not in prefix or "@" not in prefix:
			return
		nick = prefix.split("!", 1)[0]
		if nick not in self.ircd.userNicks:
			return
		sourceUser = self.ircd.users[self.ircd.userNicks[nick]]
		if not sourceUser.metadataKeyExists("account"):
			return
		accountName = sourceUser.metadataValue("account")
		if "tags" in kw:
			kw["tags"]["account"] = accountName
		else:
			kw["tags"] = { "account": accountName }

accountTag = AccountTag()