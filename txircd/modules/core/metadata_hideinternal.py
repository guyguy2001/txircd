from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class HideInternalMetadata(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "HideInternalMetadata"
	core = True
	
	def actions(self):
		return [ ("usercanseemetadata", 1000, self.denyInternal) ]
	
	def denyInternal(self, user, visibility):
		if visibility == "internal":
			return False
		return None

hideInternal = HideInternalMetadata()