from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, ipAddressToShow, ircLower, now
from zope.interface import implementer
from fnmatch import fnmatchcase
from typing import Any, Dict, Callable, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class GLine(ModuleData, XLineBase):
	name = "GLine"
	core = True
	lineType = "G"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("register", 10, self.checkLines),
		         ("changeident", 10, self.checkIdentChange),
		         ("changehost", 10, self.checkHostChange),
		         ("commandpermission-GLINE", 10, self.restrictToOper),
		         ("statsruntype-glines", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("GLINE", 1, UserGLine(self)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ADDLINE", 1, ServerAddGLine(self)),
		         ("DELLINE", 1, ServerDelGLine(self)) ]
	
	def load(self) -> None:
		self.initializeLineStorage()

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "client_ban_msg" in config and not isinstance(config["client_ban_msg"], str):
			raise ConfigValidationError("client_ban_msg", "value must be a string")
	
	def checkUserMatch(self, user: "IRCUser", mask: str, data: Optional[Dict[Any, Any]]) -> bool:
		banMask = self.normalizeMask(mask)
		userMask = ircLower("{}@{}".format(user.ident, user.host()))
		if fnmatchcase(userMask, banMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, user.realHost))
		if fnmatchcase(userMask, banMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, ipAddressToShow(user.ip)))
		if fnmatchcase(userMask, banMask):
			return True
		return False
	
	def killUser(self, user: "IRCUser", reason: str) -> None:
		self.ircd.log.info("Matched user {user.uuid} ({user.ident}@{userHost()}) against a g:line: {reason}", user=user, userHost=user.host, reason=reason)
		user.sendMessage(irc.ERR_YOUREBANNEDCREEP, self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@example.com for assistance."))
		user.disconnect("G:Lined: {}".format(reason))
	
	def checkLines(self, user: "IRCUser") -> bool:
		banReason = self.matchUser(user)
		if banReason is not None:
			self.killUser(user, banReason)
			return False
		return True
	
	def checkIdentChange(self, user: "IRCUser", oldIdent: str, fromServer: Optional["IRCServer"]) -> None:
		self.checkLines(user)
	
	def checkHostChange(self, user: "IRCUser", hostType: str, oldHost: str, fromServer: Optional["IRCServer"]) -> None:
		if user.uuid[:3] == self.ircd.serverID:
			self.checkLines(user)
	
	def restrictToOper(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-gline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

@implementer(ICommand)
class UserGLine(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("GLineParams", irc.ERR_NEEDMOREPARAMS, "GLINE", "Not enough parameters")
			return None
		
		banmask = params[0]
		if banmask in self.module.ircd.userNicks:
			targetUser = self.module.ircd.userNicks[banmask]
			banmask = "{}@{}".format(targetUser.ident, targetUser.realHost)
		else:
			if "@" not in banmask:
				banmask = "*@{}".format(banmask)
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
				user.sendMessage("NOTICE", "*** G:Line for {} is already set.".format(banmask))
				return True
			badUsers = []
			for checkUser in self.module.ircd.users.values():
				reason = self.module.matchUser(checkUser)
				if reason is not None:
					badUsers.append((checkUser, reason))
			for badUser in badUsers:
				self.module.killUser(*badUser)
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed g:line for {} has been set, to expire in {} seconds.".format(banmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent g:line for {} has been set.".format(banmask))
			return True
		if not self.module.delLine(banmask, user.hostmask()):
			user.sendMessage("NOTICE", "*** G:Line for {} doesn't exist.".format(banmask))
			return True
		user.sendMessage("NOTICE", "*** G:Line for {} has been removed.".format(banmask))
		return True

@implementer(ICommand)
class ServerAddGLine(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Any]) -> Optional[Dict[Any, Any]]:
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
class ServerDelGLine(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		return self.module.executeServerDelCommand(server, data)

glineModule = GLine()