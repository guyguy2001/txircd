from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from typing import List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, IMode)
class OpMode(ModuleData, Mode):
	name = "ChanopMode"
	core = True
	
	def channelModes(self) -> List[Union[Tuple[str, ModeType, Mode], Tuple[str, ModeType, Mode, int, str]]]:
		return [ ("o", ModeType.Status, self, 100, "@") ]
	
	def checkSet(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		return param.split(",")
	
	def checkUnset(self, channel: "IRCChannel", param: str) -> Optional[List[str]]:
		return param.split(",")

opMode = OpMode()