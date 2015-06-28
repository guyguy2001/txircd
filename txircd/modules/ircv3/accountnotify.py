from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class AccountNotify(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountNotify"
	
	def actions(self):
		return [ ("usermetadataupdate", 10, self.sendAccountNotice),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self):
		if "unloading-account-notify" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-account-notify"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("account-notify")
	
	def unload(self):
		self.ircd.dataCache["unloading-account-notify"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-account-notify"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("account-notify")
	
	def addCapability(self, capList):
		capList.append("account-notify")
	
	def sendAccountNotice(self, user, key, oldValue, value, visibility, setByUser, fromServer):
		if key != "account":
			return
		noticeUsers = set()
		noticePrefix = user.hostmask()
		for channel in user.channels:
			for noticeUser in channel.users.iterkeys():
				if noticeUser.uuid[:3] == self.ircd.serverID and noticeUser != user and "capabilities" in noticeUser.cache and "account-notify" in noticeUser.cache["capabilities"]:
					noticeUsers.add(noticeUser)
		if value:
			for noticeUser in noticeUsers:
				noticeUser.sendMessage("ACCOUNT", value, prefix=noticePrefix)
		else:
			for noticeUser in noticeUsers:
				noticeUser.sendMessage("ACCOUNT", "*", prefix=noticePrefix)

accountNotify = AccountNotify()