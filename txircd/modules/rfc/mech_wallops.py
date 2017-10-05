from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, IMode)
class Wallops(ModuleData, Mode):
	name = "Wallops"
	core = True
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("WALLOPS", 1, UserWallops(self.ircd)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("WALLOPS", 1, ServerWallops(self.ircd)) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("commandpermission-WALLOPS", 1, self.canWallops) ]
	
	def userModes(self) -> List[Tuple[str, ModeType, Mode]]:
		return [ ("w", ModeType.NoParam, self) ]
	
	def canWallops(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-wallops", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - no oper permission to run command WALLOPS")
			return False
		return None

@implementer(ICommand)
class UserWallops(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("WallopsCmd", irc.ERR_NEEDMOREPARAMS, "WALLOPS", "Not enough parameters")
			return None
		return {
			"message": " ".join(params)
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		message = data["message"]
		userPrefix = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		for u in self.ircd.users.values():
			if u.uuid[:3] == self.ircd.serverID and "w" in u.modes:
				tags = u.filterConditionalTags(conditionalTags)
				u.sendMessage("WALLOPS", message, prefix=userPrefix, to=None, tags=tags)
		self.ircd.broadcastToServers(None, "WALLOPS", message, prefix=user.uuid)
		return True

@implementer(ICommand)
class ServerWallops(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 1:
			return None
		if prefix not in self.ircd.users:
			if prefix in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		return {
			"message": params[0],
			"from": self.ircd.users[prefix]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostuser" in data:
			return True
		fromUser = data["from"]
		message = data["message"]
		userPrefix = fromUser.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", fromUser, conditionalTags)
		for user in self.ircd.users.values():
			if user.uuid[:3] == self.ircd.serverID and "w" in user.modes:
				tags = user.filterConditionalTags(conditionalTags)
				user.sendMessage("WALLOPS", message, prefix=userPrefix, to=None, tags=tags)
		self.ircd.broadcastToServers(server, "WALLOPS", message, prefix=fromUser.uuid)
		return True

wallops = Wallops()