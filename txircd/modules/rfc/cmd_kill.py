from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class KillCommand(ModuleData):
	name = "KillCommand"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("commandpermission-KILL", 1, self.restrictToOpers) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("KILL", 1, UserKill(self.ircd)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("KILL", 1, ServerKill(self.ircd)) ]
	
	def restrictToOpers(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-kill", users=[user]):
			self.ircd.log.info("User {user.uuid} ({user.nick}) tried to kill another user", user=user)
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

@implementer(ICommand)
class UserKill(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 2:
			user.sendSingleError("KillParams", irc.ERR_NEEDMOREPARAMS, "KILL", "Not enough parameters")
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("KillTarget", irc.ERR_NOSUCHNICK, params[0], "No such nick")
			return None
		return {
			"user": self.ircd.userNicks[params[0]],
			"reason": " ".join(params[1:])
		}
	
	def affectedUsers(self, user: "IRCUser", data: Dict[Any, Any]) -> List["IRCUser"]:
		return [data["user"]]
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		targetUser = data["user"]
		if targetUser.uuid[:3] == self.ircd.serverID:
			reason = data["reason"]
			targetUser.sendMessage("KILL", reason, prefix=user.hostmask())
			targetUser.disconnect("Killed by {}: {}".format(user.nick, reason))
			return True
		toServer = self.ircd.servers[targetUser.uuid[:3]]
		toServer.sendMessage("KILL", targetUser.uuid, data["reason"], prefix=user.uuid)
		return True

@implementer(ICommand)
class ServerKill(Command):
	burstQueuePriority = 55
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if prefix not in self.ircd.servers and prefix not in self.ircd.users:
			return None
		if len(params) != 2:
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		return {
			"source": prefix,
			"target": self.ircd.users[params[0]],
			"reason": params[1]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostuser" in data:
			return True
		user = data["target"]
		if user.uuid[:3] == self.ircd.serverID:
			fromID = data["source"]
			if fromID in self.ircd.servers:
				fromName = self.ircd.servers[fromID].name
			else:
				fromName = self.ircd.users[fromID].nick
			user.disconnect("Killed by {}: {}".format(fromName, data["reason"]))
			return True
		toServer = self.ircd.servers[user.uuid[:3]]
		toServer.sendMessage("KILL", user.uuid, data["reason"], prefix=data["source"])
		return True

killCmd = KillCommand()