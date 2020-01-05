from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, now, isoTime
from zope.interface import implementer
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union

@implementer(IPlugin, IModuleData, IMode)
class ChanHistory(ModuleData, Mode):
	name = "ChannelHistory"
	affectedActions = {
		"commandextra-PRIVMSG": 1,
		"commandextra-NOTICE": 1,
		"servercommandextra-PRIVMSG": 1,
		"servercommandextra-NOTICE": 1,
		"join": 1
	}

	def channelModes(self):
		return [ ("H", ModeType.Param, self) ]

	def actions(self):
		return [ ("modeactioncheck-channel-H-commandextra-PRIVMSG", 1, self.channelHasMode),
			("modeactioncheck-channel-H-commandextra-NOTICE", 1, self.channelHasMode),
			("modeactioncheck-channel-H-servercommandextra-PRIVMSG", 1, self.channelHasMode),
			("modeactioncheck-channel-H-servercommandextra-NOTICE", 1, self.channelHasMode),
			("modeactioncheck-channel-H-join", 1, self.channelHasMode) ]

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "chanhistory_maxlines" in config:
			if not isinstance(config["chanhistory_maxlines"], int) or config["chanhistory_maxlines"] < 0:
				raise ConfigValidationError("chanhistory_maxlines", "invalid number")
			elif config["chanhistory_maxlines"] > 100:
				config["chanhistory_maxlines"] = 100
				self.ircd.logConfigValidationWarning("chanhistory_maxlines", "value is too large", 100)

	def channelHasMode(self, channel: "IRCChannel", *params) -> Union[None, bool, str]:
		# We don't care about the action params here, so we have an unused *params
		if "H" in channel.modes:
			return channel.modes["H"]
		return None

	def checkSet(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		if param.count(":") != 1:
			return None
		lines, seconds = param.split(":")
		try:
			lines = int(lines)
			seconds = int(seconds)
		except ValueError:
			return None
		if lines < 1 or seconds < 0:
			return None
		if lines > self.ircd.config.get("chanhistory_maxlines", 50):
			param = "{}:{}".format(self.ircd.config.get("chanhistory_maxlines", 50), seconds)
		return [param]

	def apply(self, actionName: str, channel: "IRCChannel", param: str, *params) -> None:
		modeParam = param.split(":")
		maxLines = int(modeParam[0])
		seconds = int(modeParam[1])
		if actionName == "commandextra-PRIVMSG" or actionName == "commandextra-NOTICE":
			user, data = params
			if channel not in data["targetchans"]:
				return
			if "history" not in channel.cache:
				channel.cache["history"] = []
			channel.cache["history"].append((now(), "PRIVMSG" if actionName == "commandextra-PRIVMSG" else "NOTICE", user.hostmask(), data["targetchans"][channel]))
			if len(channel.cache["history"]) > maxLines:
				channel.cache["history"] = channel.cache["history"][-maxLines:]
		elif actionName == "servercommandextra-PRIVMSG" or actionName == "servercommandextra-NOTICE":
			fromServer, data = params
			if "tochan" not in data or channel != data["tochan"]:
				return
			if "history" not in channel.cache:
				channel.cache["history"] = []
			channel.cache["history"].append((now(), "PRIVMSG" if actionName == "servercommandextra-PRIVMSG" else "NOTICE", data["from"].hostmask(), data["message"]))
			if len(channel.cache["history"]) > maxLines:
				channel.cache["history"] = channel.cache["history"][-maxLines:]
		elif actionName == "join" and "history" in channel.cache:
			actionChannel, user, fromServer = params
			user.sendMessage("NOTICE", "*** Replaying up to {} lines of history for {}{}...".format(maxLines, channel.name, " spanning up to {} seconds".format(seconds) if seconds > 0 else ""))
			hasServerTime = "capabilities" in user.cache and "server-time" in user.cache["capabilities"]
			user.createMessageBatch("ChannelHistory", "chathistory", channel.name)
			for messageData in channel.cache["history"]:
				if seconds == 0 or now() - timedelta(seconds=seconds) < messageData[0]:
					messageArgs = {
						"prefix": messageData[2],
						"to": channel.name
					}
					if hasServerTime:
						messageArgs["tags"] = { "time": isoTime(messageData[0]) }
					user.sendMessageInBatch("ChannelHistory", messageData[1], messageData[3], **messageArgs)
			user.sendBatch("ChannelHistory")
			user.sendMessage("NOTICE", "*** End of {} channel history.".format(channel.name))

chanHistory = ChanHistory()