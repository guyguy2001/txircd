from twisted.internet import reactor
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import durationToSeconds
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class TimedModes(ModuleData, Command):
	name = "TimedModes"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modechanges-user", 10, self.handleUserModeChange),
		         ("modechanges-channel", 10, self.handleChannelModeChange) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("TIMEDMODE", 1, self) ]
	
	def load(self) -> None:
		if "user-mode-timers" not in self.ircd.dataCache:
			self.ircd.dataCache["user-mode-timers"] = {}
		if "channel-mode-timers" not in self.ircd.dataCache:
			self.ircd.dataCache["channel-mode-timers"] = {}
	
	def fullUnload(self) -> Optional["DeferredList"]:
		# Unset all timed modes
		# The intent of a timed mode is that it unsets eventually
		# But if we're doing a full unload, this is the latest we can guarantee it
		while self.ircd.dataCache["user-mode-timers"]:
			uuid = self.ircd.dataCache["user-mode-timers"].keys()[0]
			if uuid not in self.ircd.users:
				del self.ircd.dataCache["user-mode-timers"][uuid]
				continue
			user = self.ircd.users[uuid]
			userModeChanges = []
			for mode, timers in self.ircd.dataCache["user-mode-timers"][uuid].items():
				for param, timer in timers.items():
					if timer.active():
						timer.cancel()
					userModeChanges.append((False, mode, param))
			user.setModes(userModeChanges, self.ircd.serverID)
			if uuid in self.ircd.dataCache["user-mode-timers"]: # It broke, but we did all we could
				del self.ircd.dataCache["user-mode-timers"][uuid]
		while self.ircd.dataCache["channel-mode-timers"]:
			channelName = self.ircd.dataCache["channel-mode-timers"].keys()[0]
			if channelName not in self.ircd.channels:
				del self.ircd.dataCache["channel-mode-timers"][channelName]
				continue
			channel = self.ircd.channels[channelName]
			if channel.existedSince != self.ircd.dataCache["channel-mode-timers"][channelName][0]:
				del self.ircd.dataCache["channel-mode-timers"][channelName]
				continue
			channelModeChanges = []
			for mode, timers in self.ircd.dataCache["channel-mode-timers"][channelName][1].items():
				for param, timer in timers.items():
					if timer.active():
						timer.cancel()
					channelModeChanges.append((False, mode, param))
			channel.setModes(channelModeChanges, self.ircd.serverID)
			if channelName in self.ircd.dataCache["channel-mode-timers"]: # It broke, but we did all we could :(
				del self.ircd.dataCache["channel-mode-timers"][channelName]
	
	def removeUserMode(self, uuid: str, mode: str, param: Optional[str]) -> None:
		if uuid not in self.ircd.users:
			return
		user = self.ircd.users[uuid]
		user.setModes([(False, mode, param)], self.ircd.serverID)
		self.removeUserModeTimer(uuid, mode, param)
	
	def removeChannelMode(self, channelName: str, channelTime: "datetime", mode: str, param: str) -> None:
		if channelName not in self.ircd.channels:
			return
		channel = self.ircd.channels[channelName]
		if channel.existedSince != channelTime:
			return
		channel.setModes([(False, mode, param)], self.ircd.serverID)
		self.removeChannelModeTimer(channelName, channelTime, mode, param)
	
	def removeUserModeTimer(self, uuid: str, mode: str, param: str) -> None:
		if uuid not in self.ircd.dataCache["user-mode-timers"]:
			return
		if mode not in self.ircd.dataCache["user-mode-timers"][uuid]:
			return
		if param not in self.ircd.dataCache["user-mode-timers"][uuid][mode]:
			return
		timer = self.ircd.dataCache["user-mode-timers"][uuid][mode][param]
		if timer.active():
			timer.cancel()
		del self.ircd.dataCache["user-mode-timers"][uuid][mode][param]
		if not self.ircd.dataCache["user-mode-timers"][uuid][mode]:
			del self.ircd.dataCache["user-mode-timers"][uuid][mode]
			if not self.ircd.dataCache["user-mode-timers"][uuid]:
				del self.ircd.dataCache["user-mode-timers"][uuid]
	
	def removeChannelModeTimer(self, channelName: str, channelTime: "datetime", mode: str, param: str) -> None:
		if channelName not in self.ircd.dataCache["channel-mode-timers"]:
			return
		if channelTime != self.ircd.dataCache["channel-mode-timers"][channelName][0]:
			return
		if mode not in self.ircd.dataCache["channnel-mode-timers"][channelName][1]:
			return
		if param not in self.ircd.dataCache["channel-mode-timers"][channelName][1][mode]:
			return
		timer = self.ircd.dataCache["channel-mode-timers"][channelName][1][mode][param]
		if timer.active():
			timer.cancel()
		del self.ircd.dataCache["channel-mode-timers"][channelName][1][mode][param]
		if not self.ircd.dataCache["channel-mode-timers"][channelName][1][mode]:
			del self.ircd.dataCache["channel-mode-timers"][channelName][1][mode]
			if not self.ircd.dataCache["channel-mode-timers"][channelName][1]:
				del self.ircd.dataCache["channel-mode-timers"][channelName]
	
	def handleUserModeChange(self, user: "IRCUser", source: str, sourceName: str, modeChanges: List[Tuple[bool, str, str, str, "datetime"]]) -> None:
		uuid = user.uuid
		if uuid not in self.ircd.dataCache["user-mode-timers"]:
			return
		for modeChange in modeChanges:
			if modeChange[0]:
				continue # We only care about removed modes here
			mode, param = modeChange[1:3]
			self.removeUserModeTimer(uuid, mode, param)
	
	def handleChannelModeChange(self, channel: "IRCChannel", source: str, sourceName: str, modeChanges: List[Tuple[bool, str, str, str, "datetime"]]) -> None:
		channelName = channel.name
		if channelName not in self.ircd.dataCache["channel-mode-timers"]:
			return
		for modeChange in modeChanges:
			if modeChange[0]:
				continue # We only care about removed modes here
			mode, param = modeChange[1:3]
			self.removeChannelModeTimer(channelName, channel.existedSince, mode, param)
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 3:
			return None
		duration = durationToSeconds(params[1])
		if params[0] in self.ircd.channels:
			return {
				"channel": self.ircd.channels[params[0]],
				"duration": duration,
				"modes": params[2],
				"params": params[3:]
			}
		if params[0] in self.ircd.userNicks:
			targetUser = self.ircd.userNicks[params[0]]
			if targetUser != user:
				user.sendSingleError("TimedModeCmd", irc.ERR_USERSDONTMATCH, "Can't operate on modes for other users")
				return None
			return {
				"user": self.ircd.userNicks[params[0]],
				"duration": duration,
				"modes": params[2],
				"params": params[3:]
			}
		return None
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		modeList = data["modes"]
		paramList = data["params"]
		durationSeconds = data["duration"]
		if "channel" in data:
			channel = data["channel"]
			changedModes = channel.setModesByUser(user, modeList, paramList)
			for modeChange in changedModes:
				if not modeChange[0]: # We only care here about modes being set
					continue
				mode = modeChange[1]
				param = modeChange[2]
				newTimer = reactor.callLater(durationSeconds, self.removeChannelMode, channel.name, channel.existedSince, mode, param)
				if channel.name not in self.ircd.dataCache["channel-mode-timers"]:
					self.ircd.dataCache["channel-mode-timers"][channel.name] = (channel.existedSince, {})
				if mode not in self.ircd.dataCache["channel-mode-timers"][channel.name][1]:
					self.ircd.dataCache["channel-mode-timers"][channel.name][1][mode] = {}
				if param in self.ircd.dataCache["channel-mode-timers"][channel.mode][1][mode]:
					oldTimer = self.ircd.dataCache["channel-mode-timers"][channel.mode][1][param]
					if oldTimer.active():
						oldTimer.cancel()
				self.ircd.dataCache["channel-mode-timers"][channel.name][1][mode][param] = newTimer
			return True
		if "user" in data:
			user = data["user"]
			changedModes = user.setModesByUser(user, modeList, paramList)
			for modeChange in changedModes:
				if not modeChange[0]: # We only care here about modes being set
					continue
				mode = modeChange[1]
				param = modeChange[2]
				newTimer = reactor.callLater(durationSeconds, self.removeUserMode, user.uuid, mode, param)
				if user.uuid not in self.ircd.dataCache["user-mode-timers"]:
					self.ircd.dataCache["user-mode-timers"][user.uuid] = {}
				if mode not in self.ircd.dataCache["user-mode-timers"][user.uuid]:
					self.ircd.dataCache["user-mode-timers"][user.uuid][mode] = {}
				if param in self.ircd.dataCache["user-mode-timers"][user.uuid][mode]:
					oldTimer = self.ircd.dataCache["user-mode-timers"][user.uuid][mode][param]
					if oldTimer.active():
						oldTimer.cancel()
				self.ircd.dataCache["user-mode-timers"][user.uuid][mode][param] = newTimer
			return True
		return False

timedModes = TimedModes()