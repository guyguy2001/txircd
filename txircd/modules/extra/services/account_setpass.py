from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, ICommand)
class AccountSetPass(ModuleData, Command):
	name = "AccountSetPass"
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ACCOUNTSETPASS", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 1:
			user.sendSingleError("SetPassParams", irc.ERR_NEEDMOREPARAMS, "ACCOUNTSETPASS", "Not enough parameters")
			return None
		return {
			"newpass": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if not user.metadataKeyExists("account"):
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "SETPASS", "NOTLOGIN")
			user.sendMessage("NOTICE", "You must be logged into an account to change its password")
			return True
		accountName = user.metadataValue("account")
		newPassword = data["newpass"]
		passChangeResult = self.ircd.runActionUntilValue("accountchangepass", accountName, newPassword, None, users=[user])
		if not passChangeResult:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "SETPASS", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if passChangeResult[0]:
			user.sendMessage("NOTICE", "Password changed.")
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "SETPASS", passChangeResult[1])
		user.sendMessage("NOTICE", "Failed to change password: {}".format(passChangeResult[2]))
		return True

setPassCommand = AccountSetPass()