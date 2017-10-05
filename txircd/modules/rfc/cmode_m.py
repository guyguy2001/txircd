from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class ModeratedMode(ModuleData, Mode):
	name = "ModeratedMode"
	core = True
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("m", ModeType.NoParam, self) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-m-commandmodify-PRIVMSG", 10, self.channelHasMode),
		         ("modeactioncheck-channel-m-commandmodify-NOTICE", 10, self.channelHasMode) ]
	
	def channelHasMode(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "m" in channel.modes:
			return ""
		return None
	
	def apply(self, actionName: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> None:
		if channel.userRank(user) < 10 and channel in data["targetchans"]:
			del data["targetchans"][channel]
			user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, "Cannot send to channel (+m)")

moderatedMode = ModeratedMode()