from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class ServerTime(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ServerTime"
	
	def actions(self):
		return [ ("capabilitylist", 1, self.addCapability) ]
	
	def load(self):
		if "unloading-server-time" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-server-time"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("server-time")
	
	def unload(self):
		self.ircd.dataCache["unloading-server-time"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-server-time"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("server-time")
	
	def addCapability(self, user, capList):
		capList.append("server-time")

serverTime = ServerTime()