from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class MultiPrefix(ModuleData):
	name = "MultiPrefix"
	
	def actions(self):
		return [ ("channelstatuses", 2, self.allStatuses),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self):
		if "unloading-multi-prefix" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-multi-prefix"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("multi-prefix")
	
	def unload(self):
		self.ircd.dataCache["unloading-multi-prefix"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-multi-prefix"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("multi-prefix")
	
	def addCapability(self, user, capList):
		capList.append("multi-prefix")
	
	def allStatuses(self, channel, user, requestingUser):
		if "capabilities" not in requestingUser.cache or "multi-prefix" not in requestingUser.cache["capabilities"]:
			return None
		if user not in channel.users:
			return ""
		statusList = []
		for status in channel.users[user]["status"]:
			statusList.append(self.ircd.channelStatuses[status][0])
		return "".join(statusList)

multiPrefix = MultiPrefix()