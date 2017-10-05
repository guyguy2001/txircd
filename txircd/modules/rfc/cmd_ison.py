from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class IsonCommand(ModuleData, Command):
	name = "IsonCommand"
	core = True
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ISON", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("IsonParams", irc.ERR_NEEDMOREPARAMS, "ISON", "Not enough parameters")
			return None
		return {
			"nicks": params[:5]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		onUsers = []
		for nick in data["nicks"]:
			if nick in self.ircd.userNicks:
				onUsers.append(self.ircd.userNicks[nick].nick)
		user.sendMessage(irc.RPL_ISON, " ".join(onUsers))
		return True

isonCmd = IsonCommand()