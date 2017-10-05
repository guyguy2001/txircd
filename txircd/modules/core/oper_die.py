from twisted.internet import reactor
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class DieCommand(ModuleData, Command):
	name = "DieCommand"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("commandpermission-DIE", 1, self.checkCommandPermission) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("DIE", 1, self) ]
	
	def checkCommandPermission(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-die", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		self.ircd.log.info("Received DIE command from user {user.uuid} ({user.nick})", user=user)
		reactor.stop()
		return True

dieCmd = DieCommand()