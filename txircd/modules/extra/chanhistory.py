from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, now, isoTime
from zope.interface import implements
from datetime import timedelta

class ChanHistory(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)

	name = "ChannelHistory"
	affectedActions = {
		"commandextra-PRIVMSG": 1,
		"join": 1
	}

	def channelModes(self):
		return [ ("H", ModeType.Param, self) ]

	def actions(self):
		return [ ("modeactioncheck-channel-H-commandextra-PRIVMSG", 1, self.channelHasMode) ]

	def verifyConfig(self, config):
		if "chanhistory_maxlines" in config:
			if not isinstance(config["chanhistory_maxlines"], int) or config["chanhistory_maxlines"] < 0:
				raise ConfigValidationError("chanhistory_maxlines", "invalid number")
			elif config["chanhistory_maxlines"] > 100:
				config["chanhistory_maxlines"] = 100
				self.ircd.logConfigValidationWarning("chanhistory_maxlines", "value is too large", 100)

	def channelHasMode(self, channel, user, data):
		if "H" in channel.modes:
			return channel.modes["H"]
		return None

	def checkSet(self, channel, param):
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

	def apply(self, actionName, channel, param, *params):
		modeParam = param.split(":")
		maxLines = int(modeParam[0])
		seconds = int(modeParam[1])
		if actionName == "commandextra-PRIVMSG":
			user, data = params
			if channel not in data["targetchans"]:
				return
			if "history" not in channel.cache:
				channel.cache["history"] = []
			channel.cache["history"].append((now(), user.hostmask(), data["targetchans"][channel]))
			if len(channel.cache["history"]) > maxLines:
				channel.cache["history"] = channel.cache["history"][-maxLines:]
		elif actionName == "join" and "history" in channel.cache:
			actionChannel, user, fromServer = params
			user.sendMessage("NOTICE", "*** Replaying up to {} lines of history for {}{}...".format(maxLines, channel.name, " spanning up to {} seconds".format(seconds) if seconds > 0 else ""))
			hasServerTime = "capabilities" in user.cache and "server-time" in user.cache["capabilities"]
			for messageData in channel.cache["history"]:
				if seconds == 0 or now() - timedelta(seconds=seconds) < messageData[0]:
					user.sendMessage("PRIVMSG", messageData[2], prefix=messageData[1], to=channel.name, tags={ "server-time": isoTime(messageData[0]) } if hasServerTime else None)
			user.sendMessage("NOTICE", "*** End of {} channel history.".format(channel.name))

chanHistory = ChanHistory()