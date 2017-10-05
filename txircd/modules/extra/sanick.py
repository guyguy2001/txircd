from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import ICommand, IModuleData, Command, ModuleData
from txircd.utils import isValidNick, lenBytes
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class SanickCommand(ModuleData, Command):
	name = "SanickCommand"

	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("SANICK", 1, self) ]

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("commandpermission-SANICK", 1, self.restrictToOpers) ]

	def restrictToOpers(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-sanick", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 2:
			user.sendSingleError("SanickCmd", irc.ERR_NEEDMOREPARAMS, "SANICK", "Not enough parameters")
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("SanickCmd", irc.ERR_NOSUCHNICK, params[0], "No such nick")
			return None
		if not isValidNick(params[1]) or lenBytes(params[1]) > self.ircd.config.get("nick_length", 32):
			user.sendSingleError("SanickCmd", irc.ERR_ERRONEUSNICKNAME, params[1], "Erroneous nickname")
			return None
		if params[1] in self.ircd.userNicks:
			otherUser = self.ircd.userNicks[params[1]]
			if user != otherUser:
				user.sendSingleError("SanickCmd", irc.ERR_NICKNAMEINUSE, params[1], "Nickname is already in use")
				return None
		return {
			"target": self.ircd.userNicks[params[0]],
			"nick": params[1]
		}

	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		targetUser = data["target"]
		newNick = data["nick"]
		self.ircd.log.info("User {user.uuid} ({user.nick}) forcibly changed user {targetUser.uuid}'s nick from {targetUser.nick} to {newNick}", user=user, targetUser=targetUser, newNick=newNick)
		data["target"].changeNick(data["nick"])
		return True

sanick = SanickCommand()