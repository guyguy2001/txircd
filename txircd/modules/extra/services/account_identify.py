from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

class AccountIdentify(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountIdentify"
	
	def userCommands(self):
		return [ ("IDENTIFY", 1, IdentifyCommand(self)),
			("ID", 1, IdCommand(self)) ]
	
	def parseParams(self, command, user, params, prefix, tags):
		if not params:
			user.sendSingleError("IdentifyParams", irc.ERR_NEEDMOREPARAMS, command, "Not enough parameters")
			return None
		if len(params) == 1:
			return {
				"password": params[0]
			}
		return {
			"accountname": params[0],
			"password": params[1]
		}
	
	def execute(self, user, data):
		if "accountname" in data:
			accountName = data["accountname"]
		else:
			accountName = self.ircd.runActionUntilValue("accountfromnick", user.nick)
			if not accountName:
				user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "IDENTIFY", "NOTEXIST")
				user.sendMessage("NOTICE", "No account could be found associated with your nickname.")
				return True
		resultValue = self.ircd.runActionUntilValue("accountauthenticate", user, accountName, data["password"])
		if not resultValue:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "IDENTIFY", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if resultValue[0] is None:
			resultValue[1].addCallback(self.checkAuthSuccess, user)
			return True
		if resultValue[0]:
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "IDENTIFY", resultValue[1])
		user.sendMessage("NOTICE", resultValue[2])
		return True
	
	def checkAuthSuccess(self, result, user):
		if user.uuid not in self.ircd.users:
			return
		loginSuccess, errorCode, errorMessage = result
		if loginSuccess:
			return
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "IDENTITY", errorCode)
		user.sendMessage("NOTICE", errorMessage)

class IdentifyCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		return self.module.parseParams("IDENTIFY", user, params, prefix, tags)
	
	def execute(self, user, data):
		return self.module.execute(user, data)

class IdCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		return self.module.parseParams("ID", user, params, prefix, tags)
	
	def execute(self, user, data):
		self.module.execute(user, data)

identifyCommand = AccountIdentify()