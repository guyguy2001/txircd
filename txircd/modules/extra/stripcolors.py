from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, stripFormatting
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class StripColors(ModuleData, Mode):
	name = "StripColors"
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}

	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("S", ModeType.NoParam, self) ]

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-S-commandmodify-PRIVMSG", 10, self.channelHasMode),
		         ("modeactioncheck-channel-S-commandmodify-NOTICE", 10, self.channelHasMode) ]

	def channelHasMode(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "S" in channel.modes:
			return ""
		return None

	def apply(self, actionName: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> None:
		if channel in data["targetchans"] and not self.ircd.runActionUntilValue("checkexemptchanops", "stripcolor", channel, user):
			message = data["targetchans"][channel]
			data["targetchans"][channel] = stripFormatting(message)

stripColors = StripColors()