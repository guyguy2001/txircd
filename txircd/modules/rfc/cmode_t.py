from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class TopicLockMode(ModuleData, Mode):
	name = "TopicLockMode"
	core = True
	affectedActions = { "commandpermission-TOPIC": 10 }
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("t", ModeType.NoParam, self) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-t-commandpermission-TOPIC", 10, self.channelHasMode) ]
	
	def channelHasMode(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "t" in channel.modes:
			return ""
		return None
	
	def apply(self, actionType: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if "topic" not in data:
			return None
		if not self.ircd.runActionUntilValue("checkchannellevel", "topic", channel, user, users=[user], channels=[channel]):
			user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, "You do not have access to change the topic on this channel")
			return False
		return None

topicLockMode = TopicLockMode()