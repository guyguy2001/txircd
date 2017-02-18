from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

class AccountName(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "AccountName"
	
	def userCommands(self):
		return [ ("ACCOUNTNAME", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		if not params or not params[0]:
			user.sendSingleError("AccountNameParams", irc.ERR_NEEDMOREPARAMS, "ACCOUNTNAME", "Not enough parameters")
			return None
		return {
			"name": params[0]
		}
	
	def execute(self, user, data):
		userAccount = user.metadataValue("account")
		if not userAccount:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "NAME", "NOTLOGIN")
			user.sendMessage("NOTICE", "You're not logged in.")
			return True
		nameChangeResult = self.ircd.runActionUntilValue("accountchangename", userAccount, data["name"])
		if not nameChangeResult:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "NAME", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if nameChangeResult[0]:
			user.sendMessage("NOTICE", "Your account name has been updated.")
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "NAME", nameChangeResult[1])
		user.sendMessage("NOTICE", "Couldn't set your account name: {}".format(nameChangeResult[2]))
		return True

nameChangeCommand = AccountName()