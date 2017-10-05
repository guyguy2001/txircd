from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class SnoOper(ModuleData, Command):
	name = "ServerNoticeOper"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("oper", 1, self.sendOperNotice),
		         ("operfail", 1, self.sendOperFailNotice),
		         ("servernoticetype", 1, self.checkSnoType) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("OPERFAILNOTICE", 1, self) ]
	
	def sendOperNotice(self, user: "IRCUser") -> None:
		if user.uuid[:3] == self.ircd.serverID:
			mask = "oper"
			message = "{} has opered.".format(user.nick)
		else:
			mask = "remoteoper"
			message = "{} has opered. (from {})".format(user.nick, self.ircd.servers[user.uuid[:3]].name)
		self.ircd.runActionStandard("sendservernotice", mask, message)
	
	def sendOperFailNotice(self, user: "IRCUser", reason: str) -> None:
		self.ircd.runActionStandard("sendservernotice", "oper", "Failed OPER attempt from {} ({})".format(user.nick, reason))
		self.ircd.broadcastToServers(None, "OPERFAILNOTICE", user.uuid, reason, prefix=self.ircd.serverID)
	
	def checkSnoType(self, user: "IRCUser", typename: str) -> bool:
		if typename == "oper":
			return True
		if typename == "remoteoper":
			return True
		return False
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		if prefix not in self.ircd.servers:
			return None
		if params[0] not in self.ircd.users:
			# Since this should always come from the server the user is on, we don't need to worry about recently quit users
			return None
		return {
			"fromserver": self.ircd.servers[prefix],
			"user": self.ircd.users[params[0]],
			"reason": params[1]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		user = data["user"]
		reason = data["reason"]
		fromServer = data["fromserver"]
		self.ircd.runActionStandard("sendservernotice", "remoteoper", "Failed OPER attempt from {} ({}) (from {})".format(user.nick, reason, fromServer.name))
		self.ircd.broadcastToServers(server, "OPERFAILNOTICE", user.uuid, reason, prefix=fromServer.serverID)
		return True

snoOper = SnoOper()