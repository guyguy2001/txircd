from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, ipAddressToShow, now
from zope.interface import implementer
from fnmatch import fnmatchcase
from typing import Any, Callable, Dict, List, Optional, Tuple
import socket

@implementer(IPlugin, IModuleData)
class ZLine(ModuleData, XLineBase):
	name = "ZLine"
	core = True
	lineType = "Z"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("userconnect", 10, self.checkLines),
		         ("commandpermission-ZLINE", 10, self.restrictToOper),
		         ("statsruntype-zlines", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ZLINE", 1, UserZLine(self)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ADDLINE", 1, ServerAddZLine(self)),
		         ("DELLINE", 1, ServerDelZLine(self)) ]
	
	def load(self) -> None:
		self.initializeLineStorage()

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "client_ban_msg" in config and not isinstance(config["client_ban_msg"], str):
			raise ConfigValidationError("client_ban_msg", "value must be a string")
	
	def checkUserMatch(self, user: "IRCUser", mask: str, data: Optional[Dict[Any, Any]]) -> bool:
		return fnmatchcase(ipAddressToShow(user.ip), mask)
	
	def normalizeMask(self, mask: str) -> str:
		if ":" in mask and "*" not in mask and "?" not in mask: # Normalize non-wildcard IPv6 addresses
			try:
				return socket.inet_ntop(socket.AF_INET6, socket.inet_pton(socket.AF_INET6, mask)).lower()
			except socket.error:
				return mask.lower()
		return mask.lower()
	
	def killUser(self, user: "IRCUser", reason: str) -> None:
		self.ircd.log.info("Matched user {user.uuid} ({ip}) against a z:line: {reason}", user=user, ip=ipAddressToShow(user.ip), reason=reason)
		user.sendMessage(irc.ERR_YOUREBANNEDCREEP, self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@example.com for assistance."))
		user.disconnect("Z:Lined: {}".format(reason))
	
	def checkLines(self, user: "IRCUser") -> bool:
		reason = self.matchUser(user)
		if reason is not None:
			self.killUser(user, reason)
			return False
		return True
	
	def restrictToOper(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-zline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

@implementer(ICommand)
class UserZLine(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("ZLineParams", irc.ERR_NEEDMOREPARAMS, "ZLINE", "Not enough parameters")
			return None
		banmask = params[0]
		if banmask in self.module.ircd.userNicks:
			banmask = ipAddressToShow(self.module.ircd.userNicks[banmask].ip)
		if len(params) == 1:
			return {
				"mask": banmask
			}
		return {
			"mask": banmask,
			"duration": durationToSeconds(params[1]),
			"reason": " ".join(params[2:])
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		banmask = data["mask"]
		if "reason" in data:
			if not self.module.addLine(banmask, now(), data["duration"], user.hostmask(), data["reason"]):
				user.sendMessage("NOTICE", "*** Z:Line for {} is already set.".format(banmask))
				return True
			badUsers = []
			for checkUser in self.module.ircd.users.values():
				reason = self.module.matchUser(checkUser)
				if reason is not None:
					badUsers.append((checkUser, reason))
			for badUser in badUsers:
				self.module.killUser(*badUser)
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed z:line for {} has been set, to expire in {} seconds.".format(banmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent z:line for {} has been set.".format(banmask))
			return True
		if not self.module.delLine(banmask, user.hostmask()):
			user.sendMessage("NOTICE", "*** Z:Line for {} doesn't exist.".format(banmask))
			return True
		user.sendMessage("NOTICE", "*** Z:Line for {} has been removed.".format(banmask))
		return True

@implementer(ICommand)
class ServerAddZLine(Command):
	def __init__(self, module):
		self.module = module
		self.burstQueuePriority = module.burstQueuePriority
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.handleServerAddParams(server, params, prefix, tags)
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if self.module.executeServerAddCommand(server, data):
			badUsers = []
			for user in self.module.ircd.users.values():
				reason = self.module.matchUser(user)
				if reason is not None:
					badUsers.append((user, reason))
			for user in badUsers:
				self.module.killUser(*user)
			return True
		return False

@implementer(ICommand)
class ServerDelZLine(Command):
	def __init__(self, module):
		self.module = module
		self.burstQueuePriority = module.burstQueuePriority
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		return self.module.executeServerDelCommand(server, data)

zlineModule = ZLine()