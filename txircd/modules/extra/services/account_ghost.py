from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, ICommand)
class AccountGhost(ModuleData, Command):
	name = "AccountGhost"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("commandpermission-GHOST", 1, self.checkAccount) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("GHOST", 1, self) ]
	
	def checkAccount(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not user.metadataKeyExists("account"):
			user.startErrorBatch("GhostAccount")
			user.sendBatchedError("GhostAccount", irc.ERR_SERVICES, "ACCOUNT", "GHOST", "NOTLOGIN")
			user.sendBatchedError("NOTICE", "You're not logged into an account.")
			return False
		targetUser = data["targetuser"]
		if not targetUser.metadataKeyExists("account") or targetUser.metadataValue("account") != user.metadataValue("account"):
			user.startErrorBatch("GhostAccount")
			user.sendBatchedError("GhostAccount", irc.ERR_SERVICES, "ACCOUNT", "GHOST", "WRONGACCOUNT")
			user.sendBatchedError("NOTICE", "You're not logged into the same account.")
			return False
		return None
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("GhostNick", irc.ERR_NOSUCHNICK, params[0], "No such nick")
			return None
		return {
			"targetuser": self.ircd.userNicks[params[0]]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		targetUser = data["targetuser"]
		targetUser.disconnect("Ghost removed by {}".format(user.nick))
		return True

ghostCommand = AccountGhost()