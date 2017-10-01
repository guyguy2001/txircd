from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class InviteNotify(ModuleData):
	name = "InviteNotify"
	
	def actions(self):
		return [ ("capabilitylist", 10, self.addCapability),
		         ("notifyinvite", 10, self.sendInviteNotify) ]
	
	def load(self):
		if "unloading-invite-notify" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-invite-notify"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("invite-notify")
	
	def unload(self):
		self.ircd.dataCache["unloading-invite-notify"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-invite-notify"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("invite-notify")
	
	def addCapability(self, user, capList):
		capList.append("invite-notify")
	
	def sendInviteNotify(self, userList, channel, sendingUser, invitedUser):
		sentToUsers = []
		userPrefix = sendingUser.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", sendingUser, conditionalTags)
		for user in userList:
			if "capabilities" in user.cache and "invite-notify" in user.cache["capabilities"]:
				tags = user.filterConditionalTags(conditionalTags)
				user.sendMessage("INVITE", channel.name, to=invitedUser.nick, prefix=userPrefix, tags=tags)
				sentToUsers.append(user)
		for user in sentToUsers:
			userList.remove(user)

invNotify = InviteNotify()