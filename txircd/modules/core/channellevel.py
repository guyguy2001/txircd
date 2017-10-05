from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, Optional

@implementer(IPlugin, IModuleData)
class ChannelLevel(ModuleData):
	name = "ChannelLevel"
	core = True
	
	def actions(self):
		return [ ("checkchannellevel", 1, self.levelCheck),
		         ("checkexemptchanops", 1, self.exemptCheck) ]

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "channel_minimum_level" in config and not isinstance(config["channel_minimum_level"], dict):
			raise ConfigValidationError("channel_minimum_level", "value must be a dictionary")
		if "channel_exempt_level" in config and not isinstance(config["channel_exempt_level"], dict):
			raise ConfigValidationError("channel_exempt_level", "value must be a dictionary")
	
	def minLevelFromConfig(self, configKey: str, checkType: str, defaultLevel: int) -> Optional[int]:
		configLevel = self.ircd.config.get(configKey, {}).get(checkType, defaultLevel)
		try:
			minLevel = int(configLevel)
		except ValueError:
			if configLevel not in self.ircd.channelStatuses:
				return None # If the status doesn't exist, then, to be safe, we must assume NOBODY is above the line.
			minLevel = self.ircd.channelStatuses[configLevel][1]
		return minLevel
	
	def levelCheck(self, levelType: str, channel: "IRCChannel", user: "IRCUser") -> Optional[bool]:
		minLevel = self.minLevelFromConfig("channel_minimum_level", levelType, 100)
		if not minLevel:
			return False
		return channel.userRank(user) >= minLevel
	
	def exemptCheck(self, exemptType: str, channel: "IRCChannel", user: "IRCUser") -> Optional[bool]:
		minLevel = self.minLevelFromConfig("channel_exempt_level", exemptType, 0)
		if not minLevel:
			return False # No minimum level == no exemptions
		return channel.userRank(user) >= minLevel

chanLevel = ChannelLevel()