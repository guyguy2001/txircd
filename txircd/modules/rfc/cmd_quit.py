from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import trimStringToByteLength
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class QuitCommand(ModuleData):
	name = "QuitCommand"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("quitmessage", 10, self.sendQuitMessage),
		         ("quit", 10, self.broadcastQuit),
		         ("remotequit", 10, self.broadcastQuit) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("QUIT", 1, UserQuit(self.ircd)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("QUIT", 1, ServerQuit(self.ircd)) ]

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "quit_message_length" in config:
			if not isinstance(config["quit_message_length"], int) or config["quit_message_length"] < 0:
				raise ConfigValidationError("quit_message_length", "invalid number")
			elif config["quit_message_length"] > 370:
				config["quit_message_length"] = 370
				self.ircd.logConfigValidationWarning("quit_message_length", "value is too large", 370)
	
	def sendQuitMessage(self, sendUserList: List["IRCUser"], user: "IRCUser", reason: str, batchName: Optional[str]) -> None:
		hostmask = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		for destUser in sendUserList:
			tags = destUser.filterConditionalTags(conditionalTags)
			if batchName:
				destUser.sendMessageInBatch(batchName, "QUIT", reason, to=None, prefix=hostmask, tags=tags)
			else:
				destUser.sendMessage("QUIT", reason, to=None, prefix=hostmask, tags=tags)
		del sendUserList[:]
	
	def broadcastQuit(self, user: "IRCUser", reason: str, fromServer: "IRCServer" = None):
		if user.isRegistered():
			self.ircd.broadcastToServers(fromServer, "QUIT", reason, prefix=user.uuid)

@implementer(ICommand)
class UserQuit(Command):
	forRegistered = None
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			return {
				"reason": None
			}
		return {
			"reason": trimStringToByteLength(params[0], self.ircd.config.get("quit_message_length", 370))
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if data["reason"] is None:
			user.disconnect("Client quit")
		else:
			user.disconnect("Quit: {}".format(data["reason"]))
		return True

@implementer(ICommand)
class ServerQuit(Command):
	burstQueuePriority = 81
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if prefix not in self.ircd.users:
			if prefix in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		if len(params) != 1:
			return None
		return {
			"user": self.ircd.users[prefix],
			"reason": params[0]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostuser" not in data:
			data["user"].disconnect(data["reason"], server)
		return True

quitCommand = QuitCommand()