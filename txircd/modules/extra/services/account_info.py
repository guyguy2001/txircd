from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, ICommand)
class AccountInfo(ModuleData, Command):
	name = "AccountInfo"
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ACCOUNTINFO", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			if user.metadataKeyExists("account"):
				name = user.metadataValue("account")
			else:
				name = user.nick
		else:
			name = params[0]
		return {
			"name": name
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
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