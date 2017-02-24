from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

class AccountAdminDrop(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "AccountAdminDrop"
	
	def actions(self):
		[ ("commandpermission-ACCOUNTADMINDROP", 1, self.checkOper) ]
	
	def userCommands(self):
		return [ ("ACCOUNTADMINDROP", 1, self) ]
	
	def checkOper(self, user, data):
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "account-drop", users=[user]):
			return None
		user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
		return False
	
	def parseParams(self, user, params, prefix, tags):
		if not params or not params[0]:
			user.sendSingleError("AccountAdminDropParams", irc.ERR_NEEDMOREPARAMS, "ACCOUNTADMINDROP", "Not enough parameters")
			return None
		return {
			"accountname": params[0]
		}
	
	def execute(self, user, data):
		accountName = data["accountname"]
		deleteResult = self.ircd.runActionUntilValue("deleteaccount", accountName)
		if not deleteResult:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if deleteResult[0]:
			user.sendMessage("NOTICE", "The account was dropped.")
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", deleteResult[1])
		user.sendMessage("NOTICE", "Couldn't drop account: {}".format(deleteResult[2]))
		return True

adminDropCommand = AccountAdminDrop()