from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple
from validate_email import validate_email as validateEmail

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, ICommand)
class AccountRegister(ModuleData, Command):
	name = "AccountRegister"
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("REGISTER", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("RegisterParams", irc.ERR_NEEDMOREPARAMS, "REGISTER", "Not enough parameters")
			return None
		if len(params) >= 2:
			emailAddr = params[1]
			if not validateEmail(emailAddr):
				user.startErrorBatch("RegisterEmail")
				user.sendBatchedError("RegisterEmail", irc.ERR_SERVICES, "ACCOUNT", "EMAIL", "INVALID")
				user.sendBatchedError("RegisterEmail", "NOTICE", "The entered email address is invalid.")
				return None
			return {
				"password": params[0],
				"email": params[1]
			}
		if self.ircd.config.get("account_email_required", False):
			user.sendSingleError("RegisterEmail", irc.ERR_NEEDMOREPARAMS, "REGISTER", "Not enough parameters (email address required)")
			return None
		return {
			"password": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		createResult = self.ircd.runActionUntilValue("createnewaccount", user.nick, data["password"], None, data["email"] if "email" in data else None, user, None)
		if not createResult:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "CREATE", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if createResult[0]:
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "CREATE", createResult[1])
		user.sendMessage("NOTICE", "Your account couldn't be registered: {}".format(createResult[2]))
		return True

registerCommand = AccountRegister()