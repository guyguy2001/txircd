from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class PrivateMode(ModuleData, Mode):
	name = "PrivateMode"
	core = True
	affectedActions = { "displaychannel": 10,
	                    "showchannel-whois": 10 }
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("p", ModeType.NoParam, self) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-p-displaychannel", 1, self.chanIsPrivateList),
		         ("modeactioncheck-channel-p-showchannel-whois", 1, self.chanIsPrivateWhois) ]
	
	def chanIsPrivateList(self, channel: "IRCChannel", displayData: Dict[str, Any], sameChannel: "IRCChannel", user: "IRCUser", usedSearchMask: bool) -> Union[str, bool, None]:
		if "p" in channel.modes:
			return True
		return None
	
	def chanIsPrivateWhois(self, channel: "IRCChannel", sameChannel: "IRCChannel", queryUser: "IRCUser", targetUser: "IRCUser") -> Union[str, bool, None]:
		if "p" in channel.modes:
			return True
		return None
	
	def apply(self, actionName: str, channel: "IRCChannel", param: str, *params: Any) -> Union[None, Optional[bool]]: # Union of return value of each affected action
		if actionName == "displaychannel":
			displayData, sameChannel, user, usedSearchMask = params
			if usedSearchMask:
				displayData.clear()
			elif user not in channel.users:
				displayData["name"] = "*"
				displayData["modestopic"] = "[]"
			return
		if actionName == "showchannel-whois":
			sameChannel, queryUser, targetUser = params
			if queryUser not in channel.users:
				return False
			return None

privateMode = PrivateMode()