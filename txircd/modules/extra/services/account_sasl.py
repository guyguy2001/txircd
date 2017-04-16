from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class AccountSASL(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountSASL"
	
	def actions(self):
		return [ ("authenticatesasl-PLAIN", 1, self.checkPlain) ]
	
	def checkPlain(self, user, username, password):
		resultValue = self.ircd.runActionUntilValue("accountauthenticate", user, username, password)
		if not resultValue:
			return False
		return resultValue[0]

accountSASL = AccountSASL()