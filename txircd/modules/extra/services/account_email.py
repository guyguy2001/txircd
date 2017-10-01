from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from validate_email import validate_email as validateEmail

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, ICommand)
class AccountEmail(ModuleData, Command):
	name = "AccountEmail"
	
	def userCommands(self):
		return [ ("ACCOUNTEMAIL", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		if not validateEmail(params[0]):
			user.startErrorBatch("EmailFormat")
			user.sendBatchedError("EmailFormat", irc.ERR_SERVICES, "ACCOUNT", "EMAIL", "INVALID")
			user.sendBatchedError("EmailFormat", "NOTICE", "The provided email address is not valid.")
			return None
		return {
			"email": params[0]
		}
	
	def execute(self, user, data):
		if not user.metadataKeyExists("account"):
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "EMAIL", "NOTLOGIN")
			user.sendMessage("NOTICE", "You're not logged into an account.")
			return True
		accountName = user.metadataValue("account")
		if "email" in data:
			emailAddr = data["email"]
		else:
			emailAddr = None
		emailChangeResult = self.ircd.runActionUntilValue("accountchangeemail", accountName, emailAddr)
		if not emailChangeResult:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "EMAIL", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if emailChangeResult[0]:
			user.sendMessage("NOTICE", "Your email address has been updated.")
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "EMAIL", emailChangeResult[1])
		user.sendMessage("NOTICE", "Couldn't change email address: {}".format(emailChangeResult[2]))
		return True

accountEmailCommand = AccountEmail()