from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class ChannelKeyMode(ModuleData, Mode):
	name = "ChannelKeyMode"
	core = True
	affectedActions = { "commandmodify-JOIN": 10 }
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("k", ModeType.ParamOnUnset, self) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-k-commandmodify-JOIN", 1, self.channelPassword) ]
	
	def channelPassword(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "k" in channel.modes:
			return channel.modes["k"]
		return None
	
	def checkSet(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		if not param:
			return None
		password = param.split(" ")[0].replace(",", "")
		if not password:
			return None
		return [password]
	
	def checkUnset(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		if "k" not in channel.modes:
			return None
		if param != channel.modes["k"]:
			return None
		return [param]
	
	def apply(self, actionType: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> None:
		try:
			keyIndex = data["channels"].index(channel)
		except ValueError:
			return
		if data["keys"][keyIndex] != param:
			user.sendMessage(irc.ERR_BADCHANNELKEY, channel.name, "Cannot join channel (Incorrect channel key)")
			del data["channels"][keyIndex]
			del data["keys"][keyIndex]
	
	def showParam(self, user: "IRCUser", channel: "IRCChannel") -> str:
		if user in channel.users:
			return channel.modes["k"]
		return "*"

channelKeyMode = ChannelKeyMode()