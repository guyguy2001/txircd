from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class UserCommand(Command, ModuleData):
	name = "UserCommand"
	core = True
	forRegistered = False
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("USER", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 4:
			user.sendSingleError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", "Not enough parameters")
			return None
		if not params[3]: # Make sure the gecos isn't an empty string
			user.sendSingleError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", "Not enough parameters")
			return None
		# Trim down to guarantee ident and gecos won't be rejected by the user class for being too long
		params[0] = params[0][:self.ircd.config.get("ident_length", 12)]
		params[3] = params[3][:self.ircd.config.get("gecos_length", 128)]
		for char in params[0]: # Validate the ident
			if not char.isalnum() and char not in "-.[\]^_`{|}":
				user.sendSingleError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", "Your username is not valid") # The RFC is dumb.
				return None
		return {
			"ident": params[0],
			"gecos": params[3]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		user.changeIdent(data["ident"])
		user.changeGecos(data["gecos"])
		user.register("USER")
		return True

cmd_user = UserCommand()