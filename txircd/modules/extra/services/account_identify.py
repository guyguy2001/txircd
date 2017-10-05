from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple, Union

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData)
class AccountIdentify(ModuleData):
	name = "AccountIdentify"
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("IDENTIFY", 1, IdentifyCommand(self)),
			("ID", 1, IdCommand(self)) ]
	
	def parseParams(self, command: str, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
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
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
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
	
	def checkAuthSuccess(self, result: Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]], user: "IRCUser") -> None:
		if user.uuid not in self.ircd.users:
			return
		loginSuccess, errorCode, errorMessage = result
		if loginSuccess:
			return
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "IDENTITY", errorCode)
		user.sendMessage("NOTICE", errorMessage)

@implementer(IPlugin, IModuleData)
class IdentifyCommand(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.parseParams("IDENTIFY", user, params, prefix, tags)
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		return self.module.execute(user, data)

@implementer(ICommand)
class IdCommand(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.parseParams("ID", user, params, prefix, tags)
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		return self.module.execute(user, data)

identifyCommand = AccountIdentify()