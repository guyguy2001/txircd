from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, ipAddressToShow, ircLower, now
from zope.interface import implementer
from fnmatch import fnmatchcase
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class ELine(ModuleData, XLineBase):
	name = "ELine"
	core = True
	lineType = "E"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("verifyxlinematch", 10, self.checkException),
		         ("commandpermission-ELINE", 10, self.restrictToOper),
		         ("statsruntype-elines", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ELINE", 1, UserELine(self)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ADDLINE", 1, ServerAddELine(self)),
		         ("DELLINE", 1, ServerDelELine(self)) ]
	
	def load(self) -> None:
		self.initializeLineStorage()
	
	def checkUserMatch(self, user: "IRCUser", mask: str, data: Optional[Dict[Any, Any]]) -> bool:
		exceptMask = ircLower(mask)
		userMask = ircLower("{}@{}".format(user.ident, user.host()))
		if fnmatchcase(userMask, exceptMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, user.realHost))
		if fnmatchcase(userMask, exceptMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, ipAddressToShow(user.ip)))
		if fnmatchcase(userMask, exceptMask):
			return True
		return False
	
	def checkException(self, lineType: str, user: "IRCUser", mask: str, data: Optional[Dict[Any, Any]]) -> Optional[bool]:
		if lineType == "E":
			return None
		if self.matchUser(user) is not None and not self.ircd.runActionUntilFalse("xlinetypeallowsexempt", lineType):
			return False
		return None
	
	def restrictToOper(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-eline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

@implementer(ICommand)
class UserELine(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("ELineParams", irc.ERR_NEEDMOREPARAMS, "ELINE", "Not enough parameters")
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
				user.sendMessage("NOTICE", "*** E:Line for {} is already set.".format(banmask))
				return True
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed e:line for {} has been set, to expire in {} seconds.".format(banmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent e:line for {} has been set.".format(banmask))
			return True
		if not self.module.delLine(banmask, user.hostmask()):
			user.sendMessage("NOTICE", "*** E:Line for {} doesn't exist.".format(banmask))
			return True
		user.sendMessage("NOTICE", "*** E:Line for {} has been removed.".format(banmask))
		return True

@implementer(ICommand)
class ServerAddELine(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.handleServerAddParams(server, params, prefix, tags)
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		return self.module.executeServerAddCommand(server, data)

@implementer(ICommand)
class ServerDelELine(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		return self.module.executeServerDelCommand(server, data)

elineModule = ELine()