from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class SecretMode(ModuleData, Mode):
	name = "SecretMode"
	core = True
	affectedActions = { "displaychannel": 20,
	                    "showchannel-whois": 20 }
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("s", ModeType.NoParam, self) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-s-displaychannel", 1, self.chanIsSecretList),
		         ("modeactioncheck-channel-s-showchannel-whois", 1, self.chanIsSecretWhois) ]
	
	def chanIsSecretList(self, channel: "IRCChannel", displayData: Dict[str, Any], sameChannel: "IRCChannel", user: "IRCUser", usedSearchMask: bool) -> Union[str, bool, None]:
		if "s" in channel.modes:
			return True
		return None
	
	def chanIsSecretWhois(self, channel: "IRCChannel", sameChannel: "IRCChannel", queryUser: "IRCUser", targetUser: "IRCUser") -> Union[str, bool, None]:
		if "s" in channel.modes:
			return True
		return None
	
	def apply(self, actionName: str, channel: "IRCChannel", param: str, *params: Any) -> Union[None, Optional[bool]]: # Union of return types of each affected action
		if actionName == "displaychannel":
			displayData, sameChannel, user, usedSearchMask = params
			if user not in channel.users:
				displayData.clear() # Let's make it not show the channel at all
			return
		if actionName == "showchannel-whois":
			sameChannel, queryUser, targetUser = params
			if queryUser not in channel.users:
				return False
			return None

secretMode = SecretMode()