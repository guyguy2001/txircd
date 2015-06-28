from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ircLower
from zope.interface import implements

class Accounts(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "Accounts"
	core = True
	
	def actions(self):
		return [ ("usercansetmetadata", 10, self.denyMetadataSet) ]
	
	def denyMetadataSet(self, key):
		if ircLower(key) == "account":
			return False
		return None

accounts = Accounts()