from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, ipAddressToShow, ircLower, now
from zope.interface import implementer
from fnmatch import fnmatchcase
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class KLine(ModuleData, Command, XLineBase):
	name = "KLine"
	core = True
	lineType = "K"
	propagateToServers = False
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("register", 10, self.checkLines),
		         ("changeident", 10, self.checkIdentChange),
		         ("changehost", 10, self.checkHostChange),
		         ("commandpermission-KLINE", 10, self.restrictToOper),
		         ("statsruntype-klines", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("KLINE", 1, self) ]
	
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
		self.ircd.log.info("Matched user {user.uuid} ({user.ident}@{userHost()}) against a k:line: {reason}", user=user, userHost=user.host, reason=reason)
		user.sendMessage(irc.ERR_YOUREBANNEDCREEP, self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@example.com for assistance."))
		user.disconnect("K:Lined: {}".format(reason))
	
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
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-kline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("KLineParams", irc.ERR_NEEDMOREPARAMS, "KLINE", "Not enough parameters")
			return None
		
		banmask = params[0]
		if banmask in self.ircd.userNicks:
			targetUser = self.ircd.userNicks[banmask]
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
			if not self.addLine(banmask, now(), data["duration"], user.hostmask(), data["reason"]):
				user.sendMessage("NOTICE", "*** K:Line for {} is already set.".format(banmask))
				return True
			badUsers = []
			for checkUser in self.ircd.users.values():
				reason = self.matchUser(checkUser)
				if reason is not None:
					badUsers.append((checkUser, reason))
			for badUser in badUsers:
				self.killUser(*badUser)
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed k:line for {} has been set, to expire in {} seconds.".format(banmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent k:line for {} has been set.".format(banmask))
			return True
		if not self.delLine(banmask, user.hostmask()):
			user.sendMessage("NOTICE", "*** K:Line for {} doesn't exist.".format(banmask))
			return True
		user.sendMessage("NOTICE", "*** K:Line for {} has been removed.".format(banmask))
		return True

klineModule = KLine()