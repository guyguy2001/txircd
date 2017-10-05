from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import timestampStringFromTime
from zope.interface import implementer
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

@implementer(IPlugin, IModuleData, ICommand)
class ServerMetadata(ModuleData, Command):
	name = "ServerMetadata"
	core = True
	burstQueuePriority = 70
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("usermetadataupdate", 10, self.propagateUserMetadata),
		         ("channelmetadataupdate", 10, self.propagateChannelMetadata),
		         ("welcome", 10, self.propagateAllUserMetadata) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("METADATA", 1, self) ]
	
	def propagateMetadata(self, targetID: str, targetTime: str, key: str, value: str, fromServer: Optional["IRCServer"]) -> None:
		serverPrefix = fromServer.serverID if fromServer else self.ircd.serverID
		if value is None:
			self.ircd.broadcastToServers(fromServer, "METADATA", targetID, targetTime, key, prefix=serverPrefix)
		else:
			self.ircd.broadcastToServers(fromServer, "METADATA", targetID, targetTime, key, value, prefix=serverPrefix)
	
	def propagateUserMetadata(self, user: "IRCUser", key: str, oldValue: str, value: str, fromServer: Optional["IRCServer"]) -> None:
		if user.isRegistered():
			self.propagateMetadata(user.uuid, timestampStringFromTime(user.connectedSince), key, value, fromServer)
	
	def propagateChannelMetadata(self, channel: "IRCChannel", key: str, oldValue: str, value: str, fromServer: Optional["IRCServer"]):
		self.propagateMetadata(channel.name, timestampStringFromTime(channel.existedSince), key, value, fromServer)
	
	def propagateAllUserMetadata(self, user: "IRCUser") -> None:
		metadataList = user.metadataList()
		userID = user.uuid
		metadataTime = timestampStringFromTime(user.connectedSince)
		for key, value in metadataList:
			self.propagateMetadata(userID, metadataTime, key, value, None)
	
	def clearMetadata(self, target: Union["IRCUser", "IRCChannel"], server: "IRCServer") -> None:
		metadataToClear = target.metadataList()
		for key, value in metadataToClear:
			target.setMetadata(key, None, server)
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) not in (3, 4):
			return None
		data = {}
		if params[0] in self.ircd.users:
			data["user"] = self.ircd.users[params[0]]
		elif params[0] in self.ircd.channels:
			data["channel"] = self.ircd.channels[params[0]]
		elif params[0] in self.ircd.recentlyQuitUsers or params[0] in self.ircd.recentlyDestroyedChannels:
			return {
				"losttarget": True
			}
		else:
			return None
		try:
			data["time"] = datetime.utcfromtimestamp(float(params[1]))
		except ValueError:
			return None
		data["key"] = params[2]
		if len(params) == 4:
			data["value"] = params[3]
		return data
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "losttarget" in data:
			return True
		if "user" in data:
			target = data["user"]
			if data["time"] < target.connectedSince:
				self.clearMetadata(target, server)
				return True
		else:
			target = data["channel"]
			if data["time"] < target.existedSince:
				target.setCreationTime(data["time"], server)
				return True
		if "value" in data:
			value = data["value"]
		else:
			value = None
		return target.setMetadata(data["key"], value, server)

serverMetadata = ServerMetadata()