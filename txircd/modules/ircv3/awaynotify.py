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
	
	def addCapability(self, user, capList):
		capList.append("away-notify")
	
	def sendAwayNotice(self, user, key, oldValue, value, visibility, setByUser, fromServer):
		if key != "away":
			return
		noticeUsers = set()
		noticePrefix = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		for channel in user.channels:
			for noticeUser in channel.users.iterkeys():
				if noticeUser.uuid[:3] == self.ircd.serverID and noticeUser != user and "capabilities" in noticeUser.cache and "away-notify" in noticeUser.cache["capabilities"]:
					noticeUsers.add(noticeUser)
		if value:
			for noticeUser in noticeUsers:
				tags = noticeUser.filterConditionalTags(conditionalTags)
				noticeUser.sendMessage("AWAY", value, to=None, prefix=noticePrefix, tags=tags)
		else:
			for noticeUser in noticeUsers:
				tags = noticeUser.filterConditionalTags(conditionalTags)
				noticeUser.sendMessage("AWAY", to=None, prefix=noticePrefix, tags=tags)
	
	def tellChannelAway(self, channel, user):
		if not user.metadataKeyExists("away"):
			return
		awayReason = user.metadataValue("away")
		noticePrefix=user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		for noticeUser in channel.users.iterkeys():
			if noticeUser.uuid[:3] == self.ircd.serverID and "capabilities" in noticeUser.cache and "away-notify" in noticeUser.cache["capabilities"]:
				tags = noticeUser.filterConditionalTags(conditionalTags)
				noticeUser.sendMessage("AWAY", awayReason, to=None, prefix=noticePrefix, tags=tags)

awayNotify = AwayNotify()