from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class PassCommand(ModuleData, Command):
	name = "PassCommand"
	core = True
	forRegistered = False
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("register", 10, self.matchPassword) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("PASS", 1, self) ]

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "server_password" in config and not isinstance(config["server_password"], str):
			raise ConfigValidationError("server_password", "value must be a string")
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("PassCmd", irc.ERR_NEEDMOREPARAMS, "PASS", "Not enough parameters")
			return None
		return {
			"password": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		user.cache["password"] = data["password"]
		return True
	
	def matchPassword(self, user: "IRCUser") -> bool:
		try:
			serverPass = self.ircd.config["server_password"]
		except KeyError:
			return True
		if "password" not in user.cache or serverPass != user.cache["password"]:
			user.sendMessage("ERROR", "Closing Link: {}@{} [Access Denied]".format(user.ident, user.host()), to=None, prefix=None)
			return False
		return True

passCmd = PassCommand()