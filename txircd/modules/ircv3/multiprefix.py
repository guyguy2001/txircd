from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class MultiPrefix(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "MultiPrefix"
	
	def actions(self):
		return [ ("channelstatuses", 2, self.allStatuses),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self):
		if "cap-add" in self.ircd.moduleFunctionCache:
			self.ircd.moduleFunctionCache["cap-add"]("multi-prefix")
	
	def unload(self):
		if "cap-add" in self.ircd.moduleFunctionCache:
			self.ircd.moduleFunctionCache["cap-add"]("multi-prefix")
	
	def addCapability(self, capList):
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