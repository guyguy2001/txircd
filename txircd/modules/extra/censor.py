from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import re

irc.RPL_BADWORDADDED = "927"
irc.RPL_BADWORDREMOVED = "928"
irc.ERR_NOSUCHBADWORD = "929"

@implementer(IPlugin, IModuleData)
class Censor(ModuleData):
	name = "Censor"
	badwords = None

	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("CENSOR", 1, UserCensorCommand(self)) ]

	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("CENSOR", 1, ServerCensorCommand(self))]

	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("G", ModeType.NoParam, ChannelCensor(self)) ]

	def userModes(self) -> List[Tuple[str, ModeType, Mode]]:
		return [ ("G", ModeType.NoParam, UserCensor(self)) ]

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-G-commandmodify-PRIVMSG", 10, self.channelHasMode),
		         ("modeactioncheck-channel-G-commandmodify-NOTICE", 10, self.channelHasMode),
		         ("modeactioncheck-user-G-commandmodify-PRIVMSG", 10, self.userHasMode),
		         ("modeactioncheck-user-G-commandmodify-NOTICE", 10, self.userHasMode),
		         ("commandpermission-CENSOR", 1, self.restrictToOpers),
		         ("statsruntype-censor", 1, self.listStats),
		         ("burst", 10, self.propgateOnBurst) ]

	def restrictToOpers(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-censor", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def channelHasMode(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "G" in channel.modes:
			return True
		return None

	def userHasMode(self, user: "IRCUser", fromUser: "IRCUser", *params: Any) -> Union[str, bool, None]:
		if "G" in user.modes:
			return True
		return None

	def listStats(self) -> Dict[str, str]:
		return self.badwords

	def propgateOnBurst(self, server: "IRCServer") -> None:
		for badword, replacement in self.badwords.items():
			server.sendMessage("CENSOR", badword, replacement, prefix=self.ircd.serverID)

	def propagateBadword(self, badword: str, replacement: str) -> None:
		if replacement:
			self.ircd.broadcastToServers(None, "CENSOR", badword, replacement, prefix=self.ircd.serverID)
		else:
			self.ircd.broadcastToServers(None, "CENSOR", badword, prefix=self.ircd.serverID)

	def load(self) -> None:
		if "badwords" not in self.ircd.storage:
			self.ircd.storage["badwords"] = {}
		self.badwords = self.ircd.storage["badwords"]

@implementer(IMode)
class ChannelCensor(Mode):
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}

	def __init__(self, censor):
		self.censor = censor
		self.ircd = censor.ircd

	def apply(self, actionName: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> None:
		if "targetchans" not in data:
			return
		if channel in data["targetchans"] and not self.ircd.runActionUntilValue("checkexemptchanops", "censor", channel, user):
			message = data["targetchans"][channel]
			for mask, replacement in self.censor.badwords.items():
				message = re.sub(mask, replacement, message, flags=re.IGNORECASE)
			data["targetchans"][channel] = message

@implementer(IMode)
class UserCensor(Mode):
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}

	def __init__(self, censor):
		self.censor = censor

	def apply(self, actionName: str, targetUser: "IRCUser", param: str, user: "IRCUser", data: Dict[Any, Any]) -> None:
		if "targetusers" not in data:
			return
		if targetUser in data["targetusers"]: 
			message = data["targetusers"][targetUser]
			for mask, replacement in self.censor.badwords.items():
				message = re.sub(mask, replacement, message, flags=re.IGNORECASE)
			data["targetusers"][targetUser] = message

@implementer(ICommand)
class UserCensorCommand(Command):
	def __init__(self, censor):
		self.censor = censor

	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			user.sendSingleError("CensorCmd", irc.ERR_NEEDMOREPARAMS, "CENSOR", "Not enough parameters")
			return None
		if len(params) == 1:
			# Removing a badword
			return {
				"badword": params[0]
			}
		else:
			# Adding a badword
			return {
				"badword": params[0],
				"replacement": params[1]
			}

	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		badword = data["badword"]
		if "replacement" in data:
			replacement = data["replacement"]
			self.censor.badwords[badword] = replacement
			self.censor.ircd.storage["badwords"] = self.censor.badwords
			self.censor.propagateBadword(badword, replacement)
			user.sendMessage(irc.RPL_BADWORDADDED, badword, replacement)
		else:
			if badword not in self.censor.badwords:
				user.sendMessage(irc.ERR_NOSUCHBADWORD, badword, "That's not a bad word on the badword list")
				return True
			del self.censor.badwords[badword]
			self.censor.ircd.storage["badwords"] = self.censor.badwords
			self.censor.propagateBadword(badword, None)
			user.sendMessage(irc.RPL_BADWORDREMOVED, badword, "Badword removed")
		return True

@implementer(ICommand)
class ServerCensorCommand(Command):
	burstQueuePriority = 40

	def __init__(self, censor):
		self.censor = censor

	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) == 1:
			# Removing a badword
			badword = params[0]
			if badword not in self.censor.badwords:
				return None
			return {
				"badword": params[0]
			}
		if len(params) == 2:
			# Adding a badword
			return {
				"badword": params[0],
				"replacement": params[1]
			}
		return None

	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		badword = data["badword"]
		if "replacement" in data:
			replacement = data["replacement"]
			self.censor.badwords[badword] = replacement
			self.censor.ircd.storage["badwords"] = self.censor.badwords
			for remoteServer in self.censor.ircd.servers.values():
				if remoteServer.nextClosest == self.censor.ircd.serverID and remoteServer != server:
					remoteServer.sendMessage("CENSOR", badword, replacement, prefix=self.censor.ircd.serverID)
		else:
			del self.censor.badwords[badword]
			self.censor.ircd.storage["badwords"] = self.censor.badwords
			for remoteServer in self.censor.ircd.servers.values():
				if remoteServer.nextClosest == self.censor.ircd.serverID and remoteServer != server:
					remoteServer.sendMessage("CENSOR", badword, prefix=self.censor.ircd.serverID)
		return True

censorModule = Censor()