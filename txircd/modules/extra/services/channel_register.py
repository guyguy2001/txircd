from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.channel import IRCChannel
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import CaseInsensitiveDictionary, ModeType, now
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple, Union

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData, IMode)
class ChannelRegister(ModuleData, Mode):
	name = "ChannelRegister"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("startup", 1, self.setUpRegisteredChannels),
			("updatestoragereferences", 10, self.setStorageReferences),
			("modepermission-channel-r", 10, self.checkSettingUserAccount),
			("modechange-channel-r", 10, self.updateRegistration),
			("modechanges-channel", 10, self.updateChannelModeData),
			("topic", 10, self.updateChannelTopicData),
			("handledeleteaccount", 10, self.unregisterForAccountDelete),
			("handleaccountchangename", 10, self.updateRegistrationForAccountRename),
			("channelstatusoverride", 50, self.allowChannelOwnerToSetStatuses),
			("checkchannellevel", 50, self.channelOwnerHasHighestLevel) ]
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("r", ModeType.Param, self) ]
	
	def load(self) -> None:
		self.registeredChannels = CaseInsensitiveDictionary()
		
		if "services" not in self.ircd.storage:
			self.ircd.storage["services"] = {}
		if "channel" not in self.ircd.storage["services"]:
			self.ircd.storage["services"]["channel"] = {}
		self.setStorageReferences()
		if "data" not in self.channelData:
			self.channelData["data"] = {}
		if "index" not in self.channelData:
			self.channelData["index"] = {}
		if "regname" not in self.channelData["index"]:
			self.channelData["index"]["regname"] = {}
		
		if self.ircd.startupTime is not None:
			self.setUpRegisteredChannels()
	
	def setUpRegisteredChannels(self) -> None:
		for channelName, channelInfo in self.channelData["data"].items():
			if channelName in self.ircd.channels:
				channel = self.ircd.channels[channelName]
			else:
				channel = IRCChannel(self.ircd, channelName)
				self.ircd.channels[channelName] = channel
			if channel.topic != channelInfo["topic"]:
				topicSetter = channelInfo["topicsetter"]
				channel.setTopic(channelInfo["topic"], self.ircd.serverID)
				channel.topicSetter = topicSetter
				channel.topictime = channelInfo["topictime"]
			modeList = []
			for modeData in channelInfo["modes"]:
				modeList.append([True] + list(modeData))
			channel.setModes(modeList, self.ircd.serverID)
			self.registeredChannels[channelName] = channel
	
	def setStorageReferences(self) -> None:
		self.servicesData = self.ircd.storage["services"]
		self.channelData = self.servicesData["channel"]
	
	def checkSettingUserAccount(self, channel: "IRCChannel", user: "IRCUser", adding: bool, parameter: str) -> Optional[bool]:
		if adding:
			return None
		parameter = channel.modes["r"]
		if user.metadataValue("account") == parameter:
			return None
		user.sendMessage(irc.ERR_SERVICES, "CHANNEL", "DROP", "WRONGACCOUNT")
		user.sendMessage("NOTICE", "You can't drop the channel unless you're logged into the owning account.")
		return False
	
	def checkSet(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		result = self.ircd.runActionUntilValue("checkaccountexists", param, affectedChannels=[channel])
		if result is None:
			return None
		if result:
			# TODO: Implement cap on number of channels registered by one account
			param = self.ircd.runActionUntilValue("accountfromnick", param)
			if not param:
				return None
			return [param]
		return None
	
	def updateRegistration(self, channel: "IRCChannel", sourceID: str, adding: bool, parameter: str) -> None:
		if adding:
			if channel.name in self.channelData["data"]:
				channelInfo = self.channelData["data"][channel.name]
				oldOwnerAccount = channelInfo["regname"]
				del self.channelData["index"]["regname"][oldOwnerAccount]
			else:
				channelInfo = { "regtime": now() }
				self.channelData["data"][channel.name] = channelInfo
			channelInfo["regname"] = parameter
			channelInfo["topic"] = channel.topic
			channelInfo["topicsetter"] = channel.topicSetter
			channelInfo["topictime"] = channel.topicTime
			modes = set()
			for mode, paramData in channel.modes.items():
				modeType = self.ircd.channelModeTypes[mode]
				if modeType == ModeType.List:
					for oneParamData in paramData:
						modes.add([mode] + list(oneParamData))
				else:
					modes.add((mode, paramData))
			channelInfo["modes"] = modes
			if parameter not in self.channelData["index"]["regname"]:
				self.channelData["index"]["regname"][parameter] = []
			self.channelData["index"]["regname"][parameter].append(channel.name)
			self.registeredChannels[channel.name] = channel
		else:
			del self.channelData["data"][channel.name]
			self.channelData["index"]["regname"][parameter].remove(channel.name)
			del self.registeredChannels[channel.name]
	
	def updateChannelModeData(self, channel: "IRCChannel", sourceID: str, sourceName: str, modeChanges: Tuple[bool, str, str, str, "datetime"]) -> None:
		if channel.name not in self.channelData["data"]:
			return
		modes = self.channelData["data"][channel.name]["modes"]
		for modeChange in modeChanges:
			if modeChange[1] in self.ircd.channelStatuses:
				continue
			modeType = self.ircd.channelModeTypes[modeChange[1]]
			if modeType != ModeType.List:
				modeChange = modeChange[:3] # Only keep the setter and time information for list modes
			if modeChange[0]:
				modes.add(modeChange[1:])
			else:
				modes.discard(modeChange[1:])
		self.channelData["data"][channel.name]["modes"] = modes
	
	def updateChannelTopicData(self, channel: "IRCChannel", setter: str, setterName: str, oldTopic: str) -> None:
		if channel.name not in self.channelData["data"]:
			return
		channelInfo = self.channelData["data"][channel.name]
		channelInfo["topic"] = channel.topic
		channelInfo["topicsetter"] = setterName
		channelInfo["topictime"] = channel.topicTime
	
	def unregisterForAccountDelete(self, accountName: str) -> None:
		if accountName not in self.channelData["index"]["regname"]:
			return
		for channelName in self.channelData["index"]["regname"][accountName]:
			if channelName in self.ircd.channels:
				self.ircd.channels[channelName].setModes((False, "r", None), self.ircd.serverID)
			else:
				del self.channelData["data"][channelName]
		del self.channelData["index"]["regname"][accountName]
	
	def updateRegistrationForAccountRename(self, oldAccountName: str, newAccountName: str) -> None:
		if oldAccountName not in self.channelData["index"]["regname"]:
			return
		for channelName in self.channelData["index"]["regname"][oldAccountName]:
			if channelName in self.ircd.channels:
				self.ircd.channels[channelName].setModes((True, "r", newAccountName), self.ircd.serverID)
			else:
				self.channelData["data"][channelName]["regname"] = newAccountName
				for modeData in self.channelData["data"][channelName]["modes"]:
					if modeData[0] == "r":
						modeData[1] = newAccountName
		self.channelData["index"]["regname"][newAccountName] = self.channelData["index"]["regname"][oldAccountName]
		del self.channelData["index"]["regname"][oldAccountName]
	
	def allowChannelOwnerToSetStatuses(self, channel: "IRCChannel", user: "IRCUser", mode: str, parameter: str) -> Optional[bool]:
		if "r" not in channel.modes:
			return None
		channelAccount = channel.modes["r"]
		if user.metadataValue("account") == channelAccount:
			return True
		return None
	
	def channelOwnerHasHighestLevel(self, levelType: str, channel: "IRCChannel", user: "IRCUser") -> Optional[bool]:
		if "r" not in channel.modes:
			return None
		channelAccount = channel.modes["r"]
		if user.metadataValue("account") == channelAccount:
			return True
		return None

registerChannel = ChannelRegister()