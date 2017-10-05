from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import Any, Callable, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class InvisibleMode(ModuleData, Mode):
	name = "InvisibleMode"
	core = True
	affectedActions = {
		"showchanneluser": 1,
		"showuser": 1
	}
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("modeactioncheck-user-i-showchanneluser", 1, self.isInvisibleChan),
		         ("modeactioncheck-user-i-showuser", 1, self.isInvisibleUser) ]
	
	def userModes(self) -> List[Tuple[str, ModeType, Mode]]:
		return [ ("i", ModeType.NoParam, self) ]
	
	def isInvisibleChan(self, user: "IRCUser", channel: "IRCChannel", fromUser: "IRCUser", userSeeing: "IRCUser") -> Union[str, bool, None]:
		if "i" in user.modes:
			return True
		return None
	
	def isInvisibleUser(self, user: "IRCUser", fromUser: "IRCUser", userSeeing: "IRCUser") -> Union[str, bool, None]:
		if "i" in user.modes:
			return True
		return None
	
	def apply(self, actionName: str, user: "IRCUser", param: str, *params: Any) -> Optional[bool]:
		if actionName == "showchanneluser":
			return self.applyChannels(user, *params)
		return self.applyUsers(user, *params)
	
	def applyChannels(self, user: "IRCUser", channel: "IRCChannel", fromUser: "IRCUser", sameUser: "IRCUser") -> Optional[bool]:
		if user != sameUser:
			return None
		if self.ircd.runActionUntilValue("userhasoperpermission", fromUser, "override-invisible", users=[fromUser]):
			return None
		if not channel or fromUser not in channel.users:
			return False
		return None
	
	def applyUsers(self, user: "IRCUser", fromUser: "IRCUser", sameUser: "IRCUser") -> Optional[bool]:
		if user != sameUser:
			return None
		if set(fromUser.channels).intersection(user.channels): # Get the set intersection to see if there is any overlap
			return None
		return False

invisibleMode = InvisibleMode()