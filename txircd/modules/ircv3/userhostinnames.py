from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class UserhostInNames(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "UserhostInNames"
	
	def actions(self):
		return [ ("capabilitylist", 10, self.addCapability),
		         ("displaychanneluser", 10, self.showUserHostmask) ]
	
	def load(self):
		if "unloading-userhost-in-names" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-userhost-in-names"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("userhost-in-names")
	
	def unload(self):
		self.ircd.dataCache["unloading-userhost-in-names"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-userhost-in-names"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("userhost-in-names")
	
	def addCapability(self, user, capList):
		capList.append("userhost-in-names")
	
	def showUserHostmask(self, channel, showToUser, showingUser):
		if "capabilities" not in showToUser.cache or "userhost-in-names" not in showToUser.cache["capabilities"]:
			return None
		return showingUser.hostmask()

uhNames = UserhostInNames()