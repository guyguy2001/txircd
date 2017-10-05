from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class BlockChannelNotices(ModuleData, Mode):
	name = "BlockChannelNotices"
	affectedActions = {
		"commandmodify-NOTICE": 10
	}

	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("T", ModeType.NoParam, self) ]

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-T-commandmodify-NOTICE", 1, self.channelHasMode) ]

	def apply(self, actionType: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> None:
		if channel in data["targetchans"] and not self.ircd.runActionUntilValue("checkexemptchanops", "blockchannelnotice", channel, user):
			del data["targetchans"][channel]
			user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, "Cannot send NOTICE to channel (+T is set)")

	def channelHasMode(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "T" in channel.modes:
			return ""
		return None

noNoticesMode = BlockChannelNotices()