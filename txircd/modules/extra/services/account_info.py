from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, ICommand)
class AccountInfo(ModuleData, Command):
	name = "AccountInfo"
	
	def userCommands(self):
		return [ ("ACCOUNTINFO", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		if not params or not params[0]:
			user.sendSingleError("InfoParams", irc.ERR_NEEDMOREPARAMS, "ACCOUNTINFO", "Not enough parameters")
			return None
		return {
			"name": params[0]
		}
	
	def execute(self, user, data):
		queryAccount = self.ircd.runActionUntilValue("accountfromnick", data["name"])
		if not queryAccount:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "INFO", "NOTEXIST")
			user.sendMessage("NOTICE", "No account exists with that nickname.")
			return True
		registrationTime = self.ircd.runActionUntilValue("accountgetregtime", queryAccount)
		lastLoginTime = self.ircd.runActionUntilValue("accountgetlastlogin", queryAccount)
		onlineUsers = self.ircd.runActionUntilValue("accountgetusers", queryAccount)
		accountNicks = self.ircd.runActionUntilValue("accountlistnicks", queryAccount)
		
		user.sendMessage("NOTICE", "Information for {}:".format(queryAccount))
		if registrationTime is not None:
			registrationTime = registrationTime.replace(microsecond = 0)
			user.sendMessage("NOTICE", "Registered: {}".format(registrationTime))
		if onlineUsers:
			user.sendMessage("NOTICE", "Online now")
		elif lastLoginTime is not None:
			lastLoginTime = lastLoginTime.replace(microsecond = 0)
			user.sendMessage("NOTICE", "Last logged in {}".format(lastLoginTime))
		if accountNicks:
			user.sendMessage("NOTICE", "Nicknames:")
			for nickData in accountNicks:
				user.sendMessage("NOTICE", "- {}".format(nickData[0]))
		user.sendMessage("NOTICE", "End of information for {}".format(queryAccount))
		return True

accountInfo = AccountInfo()