from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

class AccountLogout(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "AccountLogout"
	
	def userCommands(self):
		return [ ("LOGOUT", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		return {}
	
	def execute(self, user, data):
		if not user.metadataKeyExists("account"):
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "LOGOUT", "ALREADYOUT")
			user.sendMessage("NOTICE", "You're not logged in.")
			return True
		self.ircd.runActionUntilTrue("accountlogout", user)
		user.sendMessage("NOTICE", "You are now logged out.")
		return True

logoutCommand = AccountLogout()