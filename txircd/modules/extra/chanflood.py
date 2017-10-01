from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, now
from zope.interface import implementer
from datetime import timedelta

@implementer(IPlugin, IModuleData, IMode)
class ChannelFlood(ModuleData, Mode):
	name = "ChannelFlood"
	affectedActions = {
		"commandextra-PRIVMSG": 10,
		"commandextra-NOTICE": 10
	}
	
	def channelModes(self):
		return [ ("f", ModeType.Param, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-f-commandextra-PRIVMSG", 10, self.channelHasMode),
		         ("modeactioncheck-channel-f-commandextra-NOTICE", 10, self.channelHasMode) ]
	
	def channelHasMode(self, channel, user, data):
		if "f" in channel.modes:
			return channel.modes["f"]
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
		if lines < 1 or seconds < 1:
			return None
		return [param]
	
	def apply(self, actionName, channel, param, user, data):
		if "targetchans" not in data or channel not in data["targetchans"]:
			return
		if self.ircd.runActionUntilValue("checkexemptchanops", "chanflood", channel, user):
			return 
		if "floodhistory" not in channel.users[user]:
			channel.users[user]["floodhistory"] = []
		
		currentTime = now()
		channel.users[user]["floodhistory"].append((data["targetchans"][channel], currentTime))
		maxLines, seconds = param.split(":")
		maxLines = int(maxLines)
		seconds = int(seconds)
		duration = timedelta(seconds=seconds)
		floodTime = currentTime - duration
		floodHistory = channel.users[user]["floodhistory"]
		
		while floodHistory:
			if floodHistory[0][1] <= floodTime:
				del floodHistory[0]
			else:
				break
		channel.users[user]["floodhistory"] = floodHistory
		if len(floodHistory) > maxLines:
			user.leaveChannel(channel, "KICK", { "byuser": False, "server": self.ircd, "reason": "Channel flood limit reached" })

chanFlood = ChannelFlood()