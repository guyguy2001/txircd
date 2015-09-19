from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class AccountTag(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountTag"
	
	def actions(self):
		return [ ("sendingusertags", 1, self.addAccountTag),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self):
		if "unloading-account-tag" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-account-tag"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("account-tag")
	
	def unload(self):
		self.ircd.dataCache["unloading-account-tag"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-account-tag"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("account-tag")
	
	def addCapability(self, user, capList):
		capList.append("account-tag")
	
	def addAccountTag(self, fromUser, conditionalTags):
		if fromUser.metadataKeyExists("account"):
			conditionalTags["account"] = (fromUser.metadataValue("account"), lambda user: "capabilities" in user.cache and "account-tag" in user.cache["capabilities"])

accountTag = AccountTag()