from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import lenBytes, ModeType
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class CustomPrefix(ModuleData, Mode):
	name = "CustomPrefix"
	prefixes = None

	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		modes = []
		self.prefixes = self.ircd.config.get("custom_prefixes", { "h": { "level": 50, "char": "%" }, "a": { "level": 150, "char": "&" }, "q" : { "level": 200, "char": "~" } })
		for prefix, prefixValue in self.prefixes.items():
			modes.append((prefix, ModeType.Status, self, prefixValue["level"], prefixValue["char"]))
		return modes

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "custom_prefixes" in config:
			if not isinstance(config["custom_prefixes"], dict):
				raise ConfigValidationError("custom_prefixes", "value must be a dictionary")
			for prefix, prefixValue in config["custom_prefixes"].items():
				if lenBytes(prefix) != 1:
					raise ConfigValidationError("custom_prefixes", "prefix value \"{}\" should be a mode character")
				if "level" not in prefixValue:
					raise ConfigValidationError("custom_prefixes", "value \"level\" for prefix \"{}\" is missing".format(prefix))
				if "char" not in prefixValue:
					raise ConfigValidationError("custom_prefixes", "value \"char\" for prefix \"{}\" is missing".format(prefix))
				if not isinstance(prefixValue["level"], int):
					raise ConfigValidationError("custom_prefixes", "prefix \"{}\" does not specify a valid level")
				if not isinstance(prefixValue["char"], str) or lenBytes(prefixValue["char"]) != 1:
					raise ConfigValidationError("custom_prefixes", "prefix \"{}\" does not specify a valid prefix character")

	def checkSet(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		return param.split(",")
	
	def checkUnset(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		return param.split(",")

customPrefix = CustomPrefix()