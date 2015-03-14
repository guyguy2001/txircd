from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType, timestamp
from zope.interface import implements

class ServerBurst(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerBurst"
	core = True
	forRegistered = False
	
	def actions(self):
		return [ ("burst", 100, self.startBurst),
				("burst", 1, self.completeBurst) ]
	
	def serverCommands(self):
		return [ ("BURST", 1, self) ]
	
	def startBurst(self, server):
		server.bursted = False
		serversByHopcount = []
		for remoteServer in self.ircd.servers.itervalues():
			hopCount = 1
			servTrace = remoteServer
			while servTrace.nextClosest != self.ircd.serverID:
				servTrace = self.ircd.servers[servTrace.nextClosest]
				hopCount += 1
			while len(serversByHopcount) < hopCount:
				serversByHopcount.append([])
			serversByHopcount[hopCount - 1].append(remoteServer)
		for hopCount in range(1, len(serversByHopcount) + 1):
			strHopCount = str(hopCount)
			for remoteServer in serversByHopcount[hopCount - 1]:
				server.sendMessage("SERVER", remoteServer.name, remoteServer.serverID, strHopCount, remoteServer.nextClosest, remoteServer.description, prefix=self.ircd.serverID)
		for user in self.ircd.users.itervalues():
			if user.localOnly:
				continue
			if not user.isRegistered():
				continue
			signonTimestamp = str(timestamp(user.connectedSince))
			nickTimestamp = str(timestamp(user.nickSince))
			modes = []
			params = []
			listModes = {}
			for mode, param in user.modes.iteritems():
				if self.ircd.userModeTypes[mode] == ModeType.List:
					listModes[mode] = param
				else:
					modes.append(mode)
					if param is not None:
						params.append(param)
			modeStr = "+{} {}".format("".join(modes), " ".join(params)) if params else "+{}".format("".join(modes))
			server.sendMessage("UID", user.uuid, signonTimestamp, user.nick, user.realHost, user.host, user.ident, user.ip, nickTimestamp, modeStr, user.gecos, prefix=self.ircd.serverID)
			for mode, paramList in listModes.iteritems():
				for param, setter, time in paramList:
					server.sendMessage("LISTMODE", user.uuid, signonTimestamp, mode, param, setter, str(timestamp(time)), prefix=self.ircd.serverID)
			server.sendMessage("ENDLISTMODE", user.uuid, prefix=self.ircd.serverID)
			for namespace, metadata in user.metadata.iteritems():
				for key, value in metadata.iteritems():
					server.sendMessage("METADATA", user.uuid, signonTimestamp, namespace, key, value, prefix=self.ircd.serverID)
		for channel in self.ircd.channels.itervalues():
			channelTimestamp = str(timestamp(channel.existedSince))
			users = []
			for user, ranks in channel.users.iteritems():
				if user.localOnly:
					continue
				users.append("{},{}".format(ranks, user.uuid))
			if not users:
				continue # Let's not sync this channel since it won't sync properly
			modes = []
			params = []
			listModes = {}
			for mode, param in channel.modes.iteritems():
				if self.ircd.channelModeTypes[mode] == ModeType.List:
					listModes[mode] = param
				else:
					modes.append(mode)
					if param is not None:
						params.append(param)
			modeStr = "+{} {}".format("".join(modes), " ".join(params)) if params else "+{}".format("".join(modes))
			server.sendMessage("FJOIN", channel.name, channelTimestamp, modeStr, " ".join(users), prefix=self.ircd.serverID)
			for mode, params in listModes.iteritems():
				for param, setter, time in params:
					server.sendMessage("LISTMODE", channel.name, channelTimestamp, mode, param, setter, str(timestamp(time)), prefix=self.ircd.serverID)
			server.sendMessage("ENDLISTMODE", channel.name, prefix=self.ircd.serverID)
			if channel.topic:
				server.sendMessage("TOPIC", channel.name, channelTimestamp, str(timestamp(channel.topicTime)), channel.topic, prefix=self.ircd.serverID)
			for namespace, metadata in channel.metadata.iteritems():
				for key, value in metadata.iteritems():
					server.sendMessage("METADATA", channel.name, channelTimestamp, namespace, key, value, prefix=self.ircd.serverID)
	
	def completeBurst(self, server):
		server.sendMessage("BURST", prefix=self.ircd.serverID)
	
	def parseParams(self, server, params, prefix, tags):
		return {}
	
	def execute(self, server, data):
		if server.serverID in self.ircd.servers:
			server.disconnect("Server {} already exists".format(server.serverID))
			return True
		if server.name in self.ircd.serverNames:
			server.disconnect("Server with name {} already exists".format(server.name))
			return True
		server.register()
		server.endBurst()
		return True

serverBurst = ServerBurst()