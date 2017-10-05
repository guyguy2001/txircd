from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType, timestampStringFromTime
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class ServerBurst(ModuleData, Command):
	name = "ServerBurst"
	core = True
	forRegistered = False
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("burst", 100, self.startBurst),
		         ("burst", 1, self.completeBurst) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("BURST", 1, self) ]
	
	def startBurst(self, server: "IRCServer") -> None:
		server.bursted = False
		serversByHopcount = []
		serversBurstingTo = []
		for remoteServer in self.ircd.servers.values():
			if remoteServer == server:
				continue
			hopCount = 1
			servTrace = remoteServer
			if server == servTrace:
				serversBurstingTo.append(remoteServer.serverID)
				continue # Don't count this server
			burstingRemote = False
			while servTrace.nextClosest != self.ircd.serverID:
				servTrace = self.ircd.servers[servTrace.nextClosest]
				if server == servTrace:
					burstingRemote = True
					break
				hopCount += 1
			if burstingRemote:
				serversBurstingTo.append(remoteServer.serverID)
				continue
			while len(serversByHopcount) < hopCount:
				serversByHopcount.append([])
			serversByHopcount[hopCount - 1].append(remoteServer)
		for hopCount in range(1, len(serversByHopcount) + 1):
			strHopCount = str(hopCount)
			for remoteServer in serversByHopcount[hopCount - 1]:
				server.sendMessage("SERVER", remoteServer.name, remoteServer.serverID, strHopCount, remoteServer.nextClosest, remoteServer.description, prefix=self.ircd.serverID)
		for user in self.ircd.users.values():
			if user.localOnly:
				self.ircd.log.debug("Skipping bursting user {user.nick} ({user.uuid}) for being a local-only user", user=user)
				continue
			if not user.isRegistered():
				self.ircd.log.debug("Skipping bursting user {user.uuid} for not being registered yet", user=user)
				continue
			if user.uuid[:3] in serversBurstingTo: # The remote server apparently already finished its burst (or at least enough that we know this), so we need to not send it those again.
				self.ircd.log.debug("Skipping bursting user {user.nick} ({user.uuid}) for being a user from the server to which we're bursting", user=user)
				continue
			signonTimestamp = timestampStringFromTime(user.connectedSince)
			nickTimestamp = timestampStringFromTime(user.nickSince)
			modes = []
			params = []
			listModes = {}
			for mode, param in user.modes.items():
				if self.ircd.userModeTypes[mode] == ModeType.List:
					listModes[mode] = param
				else:
					modes.append(mode)
					if param is not None:
						params.append(param)
			modeStr = "+{} {}".format("".join(modes), " ".join(params)) if params else "+{}".format("".join(modes))
			uidParams = [user.uuid, signonTimestamp, user.nick, user.realHost, user.host(), user.currentHostType(), user.ident, user.ip, nickTimestamp, "S" if user.secureConnection else "*", "+{}".format("".join(modes))]
			uidParams.extend(params)
			uidParams.append(user.gecos)
			server.sendMessage("UID", *uidParams, prefix=self.ircd.serverID)
			sentListModes = False
			for mode, paramList in listModes.items():
				for param, setter, time in paramList:
					server.sendMessage("LISTMODE", user.uuid, signonTimestamp, mode, param, setter, timestampStringFromTime(time), prefix=self.ircd.serverID)
					sentListModes = True
			if sentListModes:
				server.sendMessage("ENDLISTMODE", user.uuid, prefix=self.ircd.serverID)
			for key, value in user.metadataList():
				server.sendMessage("METADATA", user.uuid, signonTimestamp, key, value, prefix=self.ircd.serverID)
		for channel in self.ircd.channels.values():
			channelTimestamp = timestampStringFromTime(channel.existedSince)
			users = []
			for user, data in channel.users.items():
				if user.localOnly:
					continue
				if user.uuid[:3] in serversBurstingTo: # The remote server already knows about these users
					continue
				ranks = data["status"]
				users.append("{},{}".format(ranks, user.uuid))
			if not users:
				continue # Let's not sync this channel since it won't sync properly
			modes = []
			params = []
			listModes = {}
			for mode, param in channel.modes.items():
				if self.ircd.channelModeTypes[mode] == ModeType.List:
					listModes[mode] = param
				else:
					modes.append(mode)
					if param is not None:
						params.append(param)
			modeStr = "+{} {}".format("".join(modes), " ".join(params)) if params else "+{}".format("".join(modes))
			fjoinParams = [channel.name, channelTimestamp] + modeStr.split(" ") + [" ".join(users)]
			server.sendMessage("FJOIN", *fjoinParams, prefix=self.ircd.serverID)
			sentListModes = False
			for mode, params in listModes.items():
				for param, setter, time in params:
					server.sendMessage("LISTMODE", channel.name, channelTimestamp, mode, param, setter, timestampStringFromTime(time), prefix=self.ircd.serverID)
					sentListModes = True
			if sentListModes:
				server.sendMessage("ENDLISTMODE", channel.name, prefix=self.ircd.serverID)
			if channel.topic:
				server.sendMessage("TOPIC", channel.name, channelTimestamp, timestampStringFromTime(channel.topicTime), channel.topic, prefix=self.ircd.serverID)
			for key, value in channel.metadataList():
				server.sendMessage("METADATA", channel.name, channelTimestamp, key, value, prefix=self.ircd.serverID)
	
	def completeBurst(self, server: "IRCServer") -> None:
		server.sendMessage("BURST", prefix=self.ircd.serverID)
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		server.endBurst()
		return True

serverBurst = ServerBurst()