from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class ErrorResponse(ModuleData):
	name = "ErrorResponse"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("quit", 10, self.sendError) ]
	
	def sendError(self, user: "IRCUser", reason: str, fromServer: Optional["IRCServer"]) -> None:
		user.sendMessage("ERROR", "Closing Link: {}@{} [{}]".format(user.ident, user.host(), reason), to=None, prefix=None)

errorResponse = ErrorResponse()