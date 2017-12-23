from twisted.internet import reactor
from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ircLower, now
from zope.interface import implementer
from datetime import timedelta
from fnmatch import fnmatchcase
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class AccountNickProtect(ModuleData):
	name = "AccountNickProtect"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("welcome", 1, self.checkNickOnConnect),
			("changenick", 1, self.checkNickOnNickChange),
			("quit", 1, self.cancelTimerOnQuit),
			("commandpermission-NICK", 10, self.checkCanChangeNick),
			("commandpermission", 50, self.blockUnidentified),
			("commandmodify-PRIVMSG", 10, self.filterMessageTargets),
			("commandmodify-NOTICE", 10, self.filterMessageTargets) ]
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "account_nick_protect_seconds" in config:
			if not isinstance(config["account_nick_protect_seconds"], int) or config["account_nick_protect_seconds"] < 1:
				raise ConfigValidationError("account_nick_protect_seconds", "invalid number")
		if "account_nick_recover_seconds" in config:
			if not isinstance(config["account_nick_recover_seconds"], int) or config["account_nick_recover_seconds"] < 1:
				raise ConfigValidationError("account_nick_recover_seconds", "invalid number")
		if "account_nick_default_prefix" not in config:
			config["account_nick_default_prefix"] = ""
		elif not isinstance(config["account_nick_default_prefix"], str):
			raise ConfigValidationError("account_nick_default_prefix", "value must be a string")
		if "account_nick_protect_restrict" not in config or not config["account_nick_protect_restrict"]:
			config["account_nick_protect_restrict"] = False
		elif not isinstance(config["account_nick_protect_restrict"], bool):
			raise ConfigValidationError("account_nick_protect_restrict", "must be true or false")
		if "account_nick_protect_restricted_commands" in config:
			if not isinstance(config["account_nick_protect_restricted_commands"], list):
				raise ConfigValidationError("account_nick_protect_restricted_commands", "value must be a list")
			for command in config["account_nick_protect_restricted_commands"]:
				if not isinstance(command, str):
					raise ConfigValidationError("account_nick_protect_restricted_commands", "\"{}\" is not a valid command".format(command))
		if "account_nick_protect_message_targets" in config:
			if not isinstance(config["account_nick_protect_message_targets"], list):
				raise ConfigValidationError("account_nick_protect_message_targets", "value must be a list")
			for target in config["account_nick_protect_message_targets"]:
				if not isinstance(target, str):
					raise ConfigValidationError("account_nick_protect_message_targets", "list values must be strings")
	
	def checkNickOnConnect(self, user: "IRCUser") -> None:
		if not self.userSignedIntoNickAccount(user):
			self.applyNickProtection(user)
	
	def checkNickOnNickChange(self, user: "IRCUser", oldNick: str, fromServer: Optional["IRCServer"]) -> None:
		self.cancelOldProtectTimer(user)
		if not self.userSignedIntoNickAccount(user):
			self.applyNickProtection(user)
	
	def cancelTimerOnQuit(self, user: "IRCUser", reason: str, fromServer: Optional["IRCServer"]) -> None:
		self.cancelOldProtectTimer(user)
	
	def checkCanChangeNick(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if "nick-protect" not in user.cache:
			return None
		if user.cache["nick-protect"] < now():
			del user.cache["nick-protect"]
			return None
		user.sendMessage("NOTICE", "You can't change nicknames yet.")
		return False
	
	def blockUnidentified(self, user: "IRCUser", command: str, data: Dict[Any, Any]) -> Optional[bool]:
		if not self.ircd.config["account_nick_protect_restrict"]:
			return None
		if "accountNickProtectTimer" not in user.cache or not user.cache["accountNickProtectTimer"].active() or self.userSignedIntoNickAccount(user):
			return None
		if command not in self.ircd.config.get("account_nick_protect_restricted_commands", ["PING", "PONG", "IDENTIFY", "ID", "NICK", "QUIT"]):
			user.sendMessage("NOTICE", "{} is not allowed until you identify or your nick is changed".format(command))
			return False
		return None
	
	def filterMessageTargets(self, user: "IRCUser", data: Dict[Any, Any]) -> None:
		messageTargets = self.ircd.config.get("account_nick_protect_message_targets", [])
		if not messageTargets:
			return
		if "accountNickProtectTimer" not in user.cache or not user.cache["accountNickProtectTimer"].active() or self.userSignedIntoNickAccount(user):
			return
		
		userNames = []
		lowerUserNames = []
		if "targetusers" in data:
			for targetUser in data["targetusers"].keys():
				userNames.append(targetUser.nick)
				lowerUserNames.append(ircLower(targetUser.nick))
		channelNames = []
		lowerChannelNames = []
		if "targetchans" in data:
			for targetChannel in data["targetchans"].keys():
				channelNames.append(targetChannel.name)
				lowerChannelNames.append(ircLower(targetChannel.name))
		badUserIndices = []
		badChannelIndices = []
		for target in messageTargets:
			lowerTarget = ircLower(target)
			for index, name in enumerate(lowerUserNames):
				if not fnmatchcase(name, lowerTarget):
					badUserIndices.append(index)
			for index, name in enumerate(lowerChannelNames):
				if not fnmatchcase(name, lowerTarget):
					badChannelIndices.append(index)
		for index in badUserIndices:
			name = userNames[index]
			del data["targetusers"][name]
			user.sendMessage("NOTICE", "Sending messages to {} is not allowed until you identify or your nick is changed".format(name))
		for index in badChannelIndices:
			name = channelNames[index]
			del data["targetchans"][name]
			user.sendMessage("NOTICE", "Sending messages to {} is not allowed until you identify or your nick is changed".format(name))
	
	def applyNickProtection(self, user: "IRCUser") -> None:
		if user.uuid[:3] != self.ircd.serverID:
			return
		protectDelay = self.ircd.config.get("account_nick_protect_seconds", 30)
		user.sendMessage("NOTICE", "The nickname you're using is owned by an account to which you are not identified. Please identify to that account or change your nick in the next \x02{}\x02 seconds.".format(protectDelay))
		user.cache["accountNickProtectTimer"] = reactor.callLater(protectDelay, self.resolveNickProtection, user, user.nick)
	
	def resolveNickProtection(self, user: "IRCUser", nick: str) -> None:
		if user.nick != nick:
			return
		if self.userSignedIntoNickAccount(user):
			return
		newNick = self.ircd.config["account_nick_default_prefix"] + user.uuid
		if newNick in self.ircd.userNicks:
			user.changeNick(user.uuid)
		else:
			user.changeNick(newNick)
		recoverSeconds = self.ircd.config.get("account_nick_recover_seconds", 10)
		if recoverSeconds > 0:
			recoveryTime = timedelta(seconds = recoverSeconds)
			user.cache["nick-protect"] = now() + recoveryTime
	
	def cancelOldProtectTimer(self, user: "IRCUser") -> None:
		if "accountNickProtectTimer" not in user.cache:
			return
		if user.cache["accountNickProtectTimer"].active():
			user.cache["accountNickProtectTimer"].cancel()
		del user.cache["accountNickProtectTimer"]
	
	def userSignedIntoNickAccount(self, user: "IRCUser") -> bool:
		accountName = self.ircd.runActionUntilValue("accountfromnick", user.nick)
		if accountName is None:
			return True # Nick applies to all accounts and no-account users
		userAccount = user.metadataValue("account")
		if userAccount == accountName:
			return True
		return False

accountNickProtect = AccountNickProtect()