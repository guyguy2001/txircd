from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class EchoMessage(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "EchoMessage"
	
	def actions(self):
		return [ ("commandextra-PRIVMSG", 10, self.returnPrivMsgMessage),
		         ("commandextra-NOTICE", 10, self.returnNoticeMessage),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self):
		if "unloading-echo-message" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-echo-message"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("echo-message")
	
	def unload(self):
		self.ircd.dataCache["unloading-echo-message"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-echo-message"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("echo-message")
	
	def addCapability(self, user, capList):
		capList.append("echo-message")
	
	def returnPrivMsgMessage(self, user, data):
		self.returnMessage("PRIVMSG", user, data)
	
	def returnNoticeMessage(self, user, data):
		self.returnMessage("NOTICE", user, data)
	
	def returnMessage(self, command, user, data):
		userPrefix = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		tags = user.filterConditionalTags(conditionalTags)
		if "targetchans" in data:
			for channel, message in data["targetchans"].iteritems():
				user.sendMessage(command, channel.name, message, prefix=userPrefix, tags=tags)
		if "targetusers" in data:
			for targetUser, message in data["targetusers"].iteritems():
				user.sendMessage(command, targetUser.nick, message, prefix=userPrefix, tags=tags)

echoMessage = EchoMessage()