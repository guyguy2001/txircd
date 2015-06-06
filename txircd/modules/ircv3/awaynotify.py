from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class AwayNotify(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AwayNotify"
	
	def actions(self):
		return [ ("usermetadataupdate", 10, self.sendAwayNotice),
		         ("capabilitylist", 10, self.addCapability),
		         ("join", 10, self.tellChannelAway) ]
	
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
		noticeUsers = set()
		for channel in user.channels:
			for noticeUser in channel.users.iterkeys():
				if noticeUser != user and "capabilities" in noticeUser.cache and "away-notify" in noticeUser.cache["capabilities"]:
					noticeUsers.add(noticeUser)
		if value:
			for noticeUser in noticeUsers:
				noticeUser.sendMessage("AWAY", value, sourceuser=user)
		else:
			for noticeUser in noticeUsers:
				noticeUser.sendMessage("AWAY", sourceuser=user)
	
	def tellChannelAway(self, channel, user):
		if not user.metadataKeyExists("away"):
			return
		awayReason = user.metadataValue("away")
		for noticeUser in channel.users.iterkeys():
			if "capabilities" in noticeUser.cache and "away-notify" in noticeUser.cache["capabilities"]:
				noticeUser.sendMessage("AWAY", awayReason, sourceuser=user)

awayNotify = AwayNotify()