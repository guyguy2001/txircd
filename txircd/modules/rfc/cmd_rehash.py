from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from fnmatch import fnmatchcase
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class RehashCommand(ModuleData):
	name = "RehashCommand"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("commandpermission-REHASH", 1, self.restrictRehashToOpers) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("REHASH", 1, UserRehash(self.ircd)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("REHASH", 1, ServerRehash(self.ircd)),
		         ("REHASHNOTICE", 1, ServerRehashNotice(self.ircd)) ]
	
	def restrictRehashToOpers(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-rehash", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

@implementer(ICommand)
class UserRehash(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			return {}
		servers = []
		serverMask = params[0]
		if fnmatchcase(self.ircd.name, serverMask):
			servers.append(None)
		for server in self.ircd.servers.values():
			if fnmatchcase(server.name, serverMask):
				servers.append(server)
		if not servers:
			user.sendSingleError("RehashServer", irc.ERR_NOSUCHSERVER, params[0], "No matching servers")
			return None
		return {
			"servers": servers
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if "servers" not in data:
			self.rehashSelf(user)
			return True
		for server in data["servers"]:
			if server is None:
				self.rehashSelf(user)
			else:
				server.sendMessage("REHASH", server.serverID, prefix=user.uuid)
		return True
	
	def rehashSelf(self, user: "IRCUser") -> None:
		user.sendMessage(irc.RPL_REHASHING, self.ircd.config.fileName, "Rehashing")
		try:
			self.ircd.rehash()
		except ConfigError as e:
			message = "Rehash failed: {}".format(e)
			for messageLine in message.split("\n"):
				user.sendMessage(irc.RPL_REHASHING, self.ircd.config.fileName, messageLine)

@implementer(ICommand)
class ServerRehash(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 1:
			return None
		if params[0] == self.ircd.serverID:
			return {
				"source": prefix
			}
		if params[0] not in self.ircd.servers:
			return None
		return {
			"source": prefix,
			"server": self.ircd.servers[params[0]]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "server" in data:
			server = data["server"]
			server.sendMessage("REHASH", server.serverID, prefix=data["source"])
			return True
		source = data["source"]
		if source in self.ircd.users:
			user = self.ircd.users[source]
			self.ircd.servers[user.uuid[:3]].sendMessage("REHASHNOTICE", user.uuid, self.ircd.config.fileName, prefix=self.ircd.serverID)
		else:
			user = None
		try:
			self.ircd.rehash()
		except ConfigError as e:
			if user:
				self.ircd.servers[user.uuid[:3]].sendMessage("REHASHNOTICE", user.uuid, self.ircd.config.fileName, "Rehash failed: {}".format(e), prefix=self.ircd.serverID)
		return True

@implementer(ICommand)
class ServerRehashNotice(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) not in (2, 3):
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		if prefix not in self.ircd.servers:
			if prefix in self.ircd.recentlyQuitServers:
				return {
					"lostserver": True
				}
			return None
		if len(params) == 2:
			return {
				"fromserver": self.ircd.servers[prefix],
				"user": self.ircd.users[params[0]],
				"filename": params[1]
			}
		return {
			"fromserver": self.ircd.servers[prefix],
			"user": self.ircd.users[params[0]],
			"filename": params[1],
			"message": params[2]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostuser" in data or "lostserver" in data:
			return True
		fromServer = data["fromserver"]
		toUser = data["user"]
		if toUser.uuid[:3] == self.ircd.serverID:
			if "message" in data:
				toUser.sendMessage(irc.RPL_REHASHING, data["filename"], data["message"], prefix=fromServer.name)
			else:
				toUser.sendMessage(irc.RPL_REHASHING, data["filename"], "Rehashing", prefix=fromServer.name)
			return True
		if "message" in data:
			self.ircd.servers[toUser.uuid[:3]].sendMessage("REHASHNOTICE", toUser.uuid, data["filename"], data["message"], prefix=fromServer.serverID)
		else:
			self.ircd.servers[toUser.uuid[:3]].sendMessage("REHASHNOTICE", toUser.uuid, data["filename"], prefix=fromServer.serverID)
		return True

rehashCmd = RehashCommand()