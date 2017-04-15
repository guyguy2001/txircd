from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

class AccountInfo(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "AccountInfo"
	
	def userCommands(self):
		return [ ("ACCOUNTINFO", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		if not params or not params[0]:
			user.sendSingleError("InfoParams", irc.ERR_NEEDMOREPARAMS, "ACCOUNTINFO", "Not enough parameters")
			return None
		return {
			"accountname": params[0]
		}
	
	def execute(self, user, data):
		queryAccount = data["accountname"]
		exists = self.ircd.runActionUntilValue("checkaccountexists", queryAccount)
		if exists is None:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "INFO", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if not exists:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "INFO", "NOTEXIST")
			user.sendMessage("NOTICE", "There is no account with that name.")
			return True
		registrationTime = self.ircd.runActionUntilValue("accountgetregtime", queryAccount)
		lastLoginTime = self.ircd.runActionUntilValue("accountgetlastlogin", queryAccount)
		onlineUsers = self.ircd.runActionUntilValue("accountgetusers", queryAccount)
		accountNicks = self.ircd.runActionUntilValue("accountlistnicks", queryAccount)
		
		user.sendMessage("NOTICE", "Information for {}:".format(queryAccount))
		if registrationTime is not None:
			user.sendMessage("NOTICE", "Registered: {}".format(registrationTime))
		if onlineUsers:
			user.sendMessage("NOTICE", "Online now")
		elif lastLoginTime is not None:
			user.sendMessage("NOTICE", "Last logged in {}".format(lastLoginTime))
		if accountNicks:
			user.sendMessage("NOTICE", "Nicknames:")
			for nickData in accountNicks:
				user.sendMessage("NOTICE", "- {}".format(nickData[0]))
		user.sendMessage("NOTICE", "End of information for {}".format(queryAccount))
		return True

accountInfo = AccountInfo()