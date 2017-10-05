from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, ICommand)
class AccountName(ModuleData, Command):
	name = "AccountName"
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ACCOUNTNAME", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			user.sendSingleError("AccountNameParams", irc.ERR_NEEDMOREPARAMS, "ACCOUNTNAME", "Not enough parameters")
			return None
		return {
			"name": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
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