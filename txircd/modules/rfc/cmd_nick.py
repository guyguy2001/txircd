from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import isValidNick, lenBytes, timestampStringFromTime
from zope.interface import implementer
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData)
class NickCommand(ModuleData):
	name = "NickCommand"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("changenickmessage", 1, self.sendNickMessage),
		         ("changenick", 1, self.broadcastNickChange),
		         ("remotechangenick", 1, self.broadcastNickChange),
		         ("buildisupport", 1, self.buildISupport) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("NICK", 1, NickUserCommand(self.ircd)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("NICK", 1, NickServerCommand(self.ircd)) ]

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "nick_length" in config:
			if not isinstance(config["nick_length"], int) or config["nick_length"] < 0:
				raise ConfigValidationError("nick_length", "invalid number")
			elif config["nick_length"] > 32:
				config["nick_length"] = 32
				self.ircd.logConfigValidationWarning("nick_length", "value is too large", 32)
	
	def sendNickMessage(self, userShowList: List["IRCUser"], user: "IRCUser", oldNick: str) -> None:
		hostmask = "{}!{}@{}".format(oldNick, user.ident, user.host())
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		for targetUser in userShowList:
			tags = targetUser.filterConditionalTags(conditionalTags)
			targetUser.sendMessage("NICK", to=user.nick, prefix=hostmask, tags=tags)
		del userShowList[:]
	
	def broadcastNickChange(self, user: "IRCUser", oldNick: str, fromServer: Optional["IRCServer"]) -> None:
		self.ircd.broadcastToServers(fromServer, "NICK", timestampStringFromTime(user.nickSince), user.nick, prefix=user.uuid)

	def buildISupport(self, data: Dict[str, Union[str, int]]) -> None:
		data["NICKLEN"] = self.ircd.config.get("nick_length", 32)

@implementer(ICommand)
class NickUserCommand(Command):
	forRegistered = None
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("NickCmd", irc.ERR_NEEDMOREPARAMS, "NICK", "Not enough parameters")
			return None
		if not params[0]:
			user.sendSingleError("NickCmd", irc.ERR_NONICKNAMEGIVEN, "No nickname given")
			return None
		if not isValidNick(params[0]) or lenBytes(params[0]) > self.ircd.config.get("nick_length", 32):
			user.sendSingleError("NickCmd", irc.ERR_ERRONEUSNICKNAME, params[0], "Erroneous nickname")
			return None
		return {
			"nick": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		nick = data["nick"]
		if nick in self.ircd.userNicks:
			otherUser = self.ircd.userNicks[nick]
			if user != otherUser:
				user.sendMessage(irc.ERR_NICKNAMEINUSE, nick, "Nickname is already in use")
				return True
		
		user.changeNick(nick)
		if not user.isRegistered():
			user.register("NICK")
		return True

@implementer(ICommand)
class NickServerCommand(Command):
	burstQueuePriority = 89
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		if prefix not in self.ircd.users:
			if prefix in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		user = self.ircd.users[prefix]
		try:
			time = datetime.utcfromtimestamp(float(params[0]))
		except ValueError:
			return None
		if params[1] in self.ircd.userNicks:
			localUser = self.ircd.userNicks[params[1]]
			if localUser != user:
				if localUser.localOnly:
					allowChange = self.ircd.runActionUntilValue("localnickcollision", localUser, user, server, users=[localUser, user])
					if allowChange:
						return {
							"user": user,
							"time": time,
							"nick": params[1]
						}
					if allowChange is False:
						return {
							"user": user,
							"time": time,
							"nick": None
						}
					return None
				return None
		return {
			"user": user,
			"time": time,
			"nick": params[1]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostuser" in data:
			return True
		user = data["user"]
		newNick = data["nick"]
		if not newNick:
			return True # Handled collision by not changing the user's nick
		if newNick in self.ircd.userNicks and self.ircd.userNicks[newNick] != user:
			user.changeNick(user.uuid)
			return True
		user.changeNick(data["nick"], server)
		user.nickSince = data["time"]
		return True

cmd_nick = NickCommand()