from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Tuple

@implementer(IPlugin, IModuleData)
class DccBlock(ModuleData):
	name = "DCCBlock"

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("commandpermission-PRIVMSG", 1, self.blockDCC),
		         ("commandpermission-NOTICE", 1, self.blockDCC) ]

	def blockDCC(self, user: "IRCUser", data: Dict[Any, Any]) -> None:
		if "targetusers" in data:
			users = list(data["targetusers"].keys())
			dccBlocked = False
			for targetUser in users:
				if data["targetusers"][targetUser].upper().startswith("\x01DCC"):
					del data["targetusers"][targetUser]
					dccBlocked = True
			if dccBlocked:
				user.sendMessage("NOTICE", "DCC is not allowed on this server.")

dccBlock = DccBlock()