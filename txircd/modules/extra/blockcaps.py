from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import string

@implementer(IPlugin, IModuleData, IMode)
class BlockCaps(ModuleData, Mode):
	name = "BlockCaps"
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("B", ModeType.Param, self) ]
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-channel-B-commandmodify-PRIVMSG", 10, self.channelHasMode),
		         ("modeactioncheck-channel-B-commandmodify-NOTICE", 10, self.channelHasMode) ]
	
	def channelHasMode(self, channel: "IRCChannel", user: "IRCUser", data: Dict[Any, Any]) -> Union[str, bool, None]:
		if "B" in channel.modes:
			return ""
		return None
	
	def checkSet(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		if param.count(":") != 1:
			return None
		capsPercent, minLength = param.split(":")
		try:
			capsPercent = int(capsPercent)
			minLength = int(minLength)
		except ValueError:
			return None
		if capsPercent < 1 or capsPercent > 100 or minLength < 1:
			return None
		return [param]
	
	def apply(self, actionName: str, channel: "IRCChannel", param: str, user: "IRCUser", data: Dict[Any, Any]) -> None:
		if channel in data["targetchans"]:
			message = data["targetchans"][channel]
			messageLength = len(message)
			
			minCapsPercent, minLength = channel.modes["B"].split(":")
			if minLength > messageLength:
				return
			
			capsCount = 0
			for character in message:
				messageLength += 1
				if character == " " or character in string.ascii_uppercase or character in string.punctuation:
					capsCount += 1
			capsPercent = float(capsCount) / messageLength
			if capsPercent < minCapsPercent:
				return
			del data["targetchans"][channel]
			user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, "Your message cannot contain more than {}% capital letters/punctuation if it's longer than {} characters".format(minCapsPercent, minLength))

blockCaps = BlockCaps()