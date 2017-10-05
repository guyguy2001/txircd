from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class LimitMode(ModuleData, Mode):
	name = "LimitMode"
	core = True
	affectedActions = { "joinpermission": 10 }
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("l", ModeType.Param, self) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-l-joinpermission", 10, self.isModeSet) ]
	
	def isModeSet(self, channel: "IRCChannel", alsoChannel: "IRCChannel", user: "IRCUser") -> Union[str, bool, None]:
		if "l" in channel.modes:
			return channel.modes["l"]
		return None
	
	def checkSet(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		if param.isdigit():
			return [param]
		return None
	
	def apply(self, actionType: str, channel: "IRCChannel", param: str, alsoChannel: "IRCChannel", user: "IRCUser") -> Optional[bool]:
		try: # There may be cases when the parameter we're passed is in string form still (e.g. from modules other than this one)
			param = int(param)
		except ValueError:
			return None
		if len(channel.users) >= param:
			user.sendMessage(irc.ERR_CHANNELISFULL, channel.name, "Cannot join channel (Channel is full)")
			return False
		return None

limitMode = LimitMode()