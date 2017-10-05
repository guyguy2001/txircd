from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple, Union

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, ICommand)
class AccountDrop(ModuleData, Command):
	name = "AccountDrop"
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ACCOUNTDROP", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("DropParams", irc.ERR_NEEDMOREPARAMS, "ACCOUNTDROP", "Not enough parameters")
			return None
		return {
			"password": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if not user.metadataKeyExists("account"):
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", "NOTLOGIN")
			user.sendMessage("NOTICE", "You're not logged into an account.")
			return True
		accountName = user.metadataValue("account")
		loginResult = self.ircd.runActionUntilValue("accountauthenticate", user, accountName, data["password"], False)
		if not loginResult:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if loginResult[0] is None:
			loginResult[1].addCallback(self.checkAuthAndDrop, user, accountName)
			return True
		self.checkAuthAndDrop(loginResult, user, accountName)
		return True
	
	def checkAuthAndDrop(self, result: Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]], user: "IRCUser", accountName: str) -> None:
		if user.uuid not in self.ircd.users:
			return
		loginSuccess, errorCode, errorMessage = result
		if loginSuccess:
			deleteResult = self.ircd.runActionUntilValue("deleteaccount", accountName)
			if not deleteResult:
				user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", "NOACCOUNT")
				user.sendMessage("NOTICE", "This server doesn't have accounts set up.") # Or it does, partially, which doesn't count.
				return
			if deleteResult[0]:
				user.sendMessage("NOTICE", "Account successfully dropped.")
				return
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", deleteResult[1])
			user.sendMessage("NOTICE", "Couldn't drop account: {}".format(deleteResult[2]))
			return
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "DROP", errorCode)
		user.sendMessage("NOTICE", "Couldn't confirm drop: {}".format(errorMessage))

dropCommand = AccountDrop()