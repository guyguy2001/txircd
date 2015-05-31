from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class AwayNotify(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AwayNotify"
	
	def actions(self):
		return [ ("usermetadataupdate", 10, self.sendAwayNotice),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self):
		if "unloading-away-notify" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-away-notify"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("away-notify")
	
	def unload(self):
		self.ircd.dataCache["unloading-away-notify"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-away-notify"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("away-notify")
	
	def addCapability(self, capList):
		capList.append("away-notify")
	
	def sendAwayNotice(self, user, key, oldValue, value, visibility, setByUser, fromServer):
		if key != "away":
			return
		if value:
			for noticeUser in self.ircd.users.itervalues():
				if "capabilities" in noticeUser.cache and "away-notify" in noticeUser.cache["capabilities"]:
					noticeUser.sendMessage("AWAY", value, sourceuser=user)
		else:
			for noticeUser in self.ircd.users.itervalues():
				if "capabilities" in noticeUser.cache and "away-notify" in noticeUser.cache["capabilities"]:
					noticeUser.sendMessage("AWAY", sourceuser=user)

awayNotify = AwayNotify()