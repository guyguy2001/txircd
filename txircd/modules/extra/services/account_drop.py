from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.ERR_SERVICES = "955"

class AccountDrop(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "AccountDrop"
	
	def userCommands(self):
		return [ ("ACCOUNTDROP", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendSingleError("DropParams", irc.ERR_NEEDMOREPARAMS, "ACCOUNTDROP", "Not enough parameters")
			return None
		return {
			"password": params[0]
		}
	
	def execute(self, user, data):
		if not user.metadataKeyExists("account"):
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", "You're not logged into an account.")
			user.sendMessage("NOTICE", "You're not logged into an account.")
			return True
		accountName = user.metadataValue("account")
		loginResult = self.ircd.runActionUntilValue("accountauthenticate", user, accountName, data["password"])
		if not loginResult:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", "This server doesn't have accounts set up.")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if loginResult[0]:
			self.ircd.runActionUntilTrue("deleteaccount", accountName)
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", "Couldn't confirm drop: {}".format(loginResult[1]))
		user.sendMessage("NOTICE", "Couldn't confirm drop: {}".format(loginResult[1]))
		return True

dropCommand = AccountDrop()