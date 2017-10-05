from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd import version
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class VersionCommand(ModuleData, Command):
	name = "VersionCommand"
	core = True
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("VERSION", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		user.sendMessage(irc.RPL_VERSION, "txircd-{} {}".format(version, self.ircd.name))
		user.sendISupport()
		return True

versionCmd = VersionCommand()