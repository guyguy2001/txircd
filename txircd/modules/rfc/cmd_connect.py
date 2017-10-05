from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class ConnectCommand(ModuleData, Command):
	name = "ConnectCommand"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("commandpermission-CONNECT", 1, self.canConnect) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("CONNECT", 1, self) ]
	
	def canConnect(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-connect", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("ConnectParams", irc.ERR_NEEDMOREPARAMS, "CONNECT", "Not enough parameters")
			return None
		return {
			"server": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		serverName = data["server"]
		if serverName in self.ircd.serverNames:
			user.sendMessage("NOTICE", "*** Server {} is already on the network".format(serverName))
		elif self.ircd.connectServer(serverName):
			user.sendMessage("NOTICE", "*** Connecting to {}".format(serverName))
		else:
			user.sendMessage("NOTICE", "*** Failed to connect to {}; it's likely not configured.".format(serverName))
		return True

connectCmd = ConnectCommand()