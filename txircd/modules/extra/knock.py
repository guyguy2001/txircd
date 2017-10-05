from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, now
from zope.interface import implementer
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from weakref import WeakKeyDictionary

irc.ERR_CANNOTKNOCK  = "480"
irc.RPL_KNOCK = "710"
irc.RPL_KNOCKDLVR = "711"
irc.ERR_TOOMANYKNOCK = "712"
irc.ERR_CHANOPEN = "713"
irc.ERR_KNOCKONCHAN = "714"

@implementer(IPlugin, IModuleData)
class Knock(ModuleData):
	name = "Knock"
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("K", ModeType.NoParam, NoKnockMode()) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-K-commandpermission-KNOCK", 10, self.channelHasMode),
		         ("invite", 1, self.clearKnocksOnInvite) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("KNOCK", 1, UserKnock(self.ircd)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("KNOCK", 1, ServerKnock(self.ircd)) ]
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "knock_delay" in config and (not isinstance(config["knock_delay"], int) or config["knock_delay"] < 0):
			raise ConfigValidationError("knock_delay", "invalid number")
	
	def channelHasMode(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "K" in channel.modes:
			return ""
		return None
	
	def clearKnocksOnInvite(self, user: "IRCUser", targetUser: "IRCUser", channel: "IRCChannel") -> None:
		if "knocks" in targetUser.cache and channel in targetUser.cache["knocks"]:
			del targetUser.cache["knocks"][channel]

@implementer(ICommand)
class UserKnock(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("KnockParams", irc.ERR_NEEDMOREPARAMS, "KNOCK", "Not enough paramters")
			return None
		if params[0] not in self.ircd.channels:
			user.sendSingleError("KnockParams", irc.ERR_NOSUCHCHANNEL, params[0], "No such channel")
			return None
		return {
			"channel": self.ircd.channels[params[0]],
			"reason": " ".join(params[1:]) if len(params) > 1 else "has asked for an invite"
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		channel = data["channel"]
		self.expireKnocks(user)
		if user in channel.users:
			user.sendMessage(irc.ERR_KNOCKONCHAN, channel.name, "Can't KNOCK on {}, you are already on that channel".format(channel.name))
			return True
		if "i" not in channel.modes:
			user.sendMessage(irc.ERR_CHANOPEN, channel.name, "Can't KNOCK on {}, channel is open".format(channel.name))
			return True
		if "knocks" in user.cache and channel in user.cache["knocks"]:
			user.sendMessage(irc.ERR_TOOMANYKNOCK, channel.name, "Can't KNOCK on {} (only one KNOCK per {} seconds allowed)".format(channel.name, self.ircd.config.get("knock_delay", 300)))
			return True
		if "knocks" not in user.cache:
			user.cache["knocks"] = WeakKeyDictionary()
		user.cache["knocks"][channel] = now()
		reason = data["reason"]
		for targetUser in channel.users:
			if targetUser.uuid[:3] == self.ircd.serverID and self.ircd.runActionUntilValue("checkchannellevel", "invite", channel, targetUser, users=[targetUser], channels=[channel]):
				targetUser.sendMessage(irc.RPL_KNOCK, channel.name, user.nick, reason)
		self.ircd.broadcastToServers(None, "KNOCK", channel.name, reason, prefix=user.uuid)
		user.sendMessage(irc.RPL_KNOCKDLVR, channel.name, "Your KNOCK has been delivered")
		return True
	
	def affectedChannels(self, user: "IRCUser", data: Dict[Any, Any]) -> List["IRCChannel"]:
		return [data["channel"]]
	
	def expireKnocks(self, user: "IRCUser") -> None:
		if "knocks" not in user.cache:
			return
		expiredKnocks = []
		nowTime = now()
		timeDiff = timedelta(seconds=self.ircd.config.get("knock_delay", 300))
		for channel, knockTime in user.cache["knocks"].items():
			if knockTime + timeDiff < nowTime:
				expiredKnocks.append(channel)
		for channel in expiredKnocks:
			del user.cache["knocks"][channel]

@implementer(ICommand)
class ServerKnock(Command):
	burstQueuePriority = 72
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		if prefix not in self.ircd.users:
			return None
		if params[0] not in self.ircd.channels:
			return None
		return {
			"user": self.ircd.users[prefix],
			"channel": self.ircd.channels[params[0]],
			"message": params[1]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		channel = data["channel"]
		fromUser = data["user"]
		reason = data["message"]
		for targetUser in channel.users:
			if targetUser.uuid[:3] == self.ircd.serverID and self.ircd.runActionUntilValue("checkchannellevel", "invite", channel, targetUser, users=[targetUser], channels=[channel]):
				targetUser.sendMessage(irc.RPL_KNOCK, channel.name, fromUser.nick, reason)
		self.ircd.broadcastToServers(server, "KNOCK", channel.name, reason, prefix=fromUser.uuid)
		return True

@implementer(IMode)
class NoKnockMode(Mode):
	affectedActions = { "commandpermission-KNOCK": 10 }

	def apply(self, actionName: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		user.sendMessage(irc.ERR_CANNOTKNOCK, channel.name, "Can't KNOCK on {}, +K is set".format(channel.name))
		return False

knock = Knock()