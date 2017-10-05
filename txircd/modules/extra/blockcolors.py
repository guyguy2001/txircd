from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class BlockColors(ModuleData, Mode):
	name = "BlockColors"
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("c", ModeType.NoParam, self) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-c-commandmodify-PRIVMSG", 10, self.channelHasMode),
		         ("modeactioncheck-channel-c-commandmodify-NOTICE", 10, self.channelHasMode) ]
	
	def channelHasMode(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "c" in channel.modes:
			return ""
		return None
	
	def apply(self, actionName: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> None:
		if channel in data["targetchans"] and not self.ircd.runActionUntilValue("checkexemptchanops", "blockcolor", channel, user):
			message = data["targetchans"][channel]
			if any(c in message for c in "\x02\x1f\x16\x1d\x0f\x03"):
				del data["targetchans"][channel]
				user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, "Cannot send colors to channel (+c)")

blockColors = BlockColors()