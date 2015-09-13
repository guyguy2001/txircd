from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class ChangeHost(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ChangeHost"
	
	def action(self):
		return [ ("changehost", 1, self.updateHosts),
		         ("changeident", 1, self.updateIdents),
		         ("remotechangeident", 1, self.updateIdents),
		         ("capabilitylist", 1, self.addCapability) ]
	
	def load(self):
		if "unloading-chghost" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-chghost"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("chghost")
	
	def unload(self):
		self.ircd.dataCache["unloading-chghost"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-chghost"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("chghost")
	
	def addCapability(self, user, capList):
		capList.append("chghost")
	
	def updateHosts(self, user, hostType, oldHost, fromServer):
		userIdent = user.ident
		userHost = user.host()
		userPrefix = "{}!{}@{}".format(user.nick, userIdent, oldHost)
		self.sendToChannelUsers(user, userIdent, userHost, userPrefix)
	
	def updateIdents(self, user, oldIdent, fromServer):
		userIdent = user.ident
		userHost = user.host()
		userPrefix = "{}!{}@{}".format(user.nick, oldIdent, userHost)
		self.sendToChannelUsers(user, userIdent, userHost, userPrefix)
	
	def sendToChannelUsers(self, user, userIdent, userHost, userPrefix):
		channelUsers = set()
		for channel in user.channels:
			for chanUser in channel.users.iterkeys():
				channelUsers.add(chanUser)
		for chanUser in channelUsers:
			if "capabilities" not in chanUser.cache or "chghost" not in chanUser.cache["capabilities"]:
				continue
			chanUser.sendMessage("CHGHOST", userIdent, userHost, prefix=userPrefix)

changeHost = ChangeHost()