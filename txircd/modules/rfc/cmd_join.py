from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.channel import InvalidChannelNameError, IRCChannel
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class JoinCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "JoinCommand"
	core = True
	
	def actions(self):
		return [ ("joinmessage", 101, self.broadcastJoin),
		         ("joinmessage", 1, self.sendJoinMessage),
		         ("remotejoinrequest", 10, self.sendRJoin),
		         ("remotejoin", 10, self.propagateJoin) ]
	
	def userCommands(self):
		return [ ("JOIN", 1, JoinChannel(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("JOIN", 1, ServerJoin(self.ircd)),
				("RJOIN", 1, RemoteJoin(self.ircd)) ]
	
	def sendJoinMessage(self, messageUsers, channel, user):
		userPrefix = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		for destUser in messageUsers:
			tags = user.filterConditionalTags(conditionalTags)
			destUser.sendMessage("JOIN", to=channel.name, prefix=userPrefix, tags=tags)
		del messageUsers[:]
	
	def sendRJoin(self, user, channel):
		self.ircd.servers[user.uuid[:3]].sendMessage("RJOIN", user.uuid, channel.name, prefix=self.ircd.serverID)
		return True
	
	def broadcastJoin(self, messageUsers, channel, user):
		userClosest = None
		if user.uuid[:3] != self.ircd.serverID:
			userClosest = self.ircd.servers[user.uuid[:3]]
			while userClosest.nextClosest != self.ircd.serverID:
				userClosest = self.ircd.servers[userClosest.nextClosest]
		self.ircd.broadcastToServers(userClosest, "JOIN", channel.name, prefix=user.uuid)
	
	def propagateJoin(self, channel, user):
		fromServer = self.ircd.servers[user.uuid[:3]]
		while fromServer.nextClosest != self.ircd.serverID:
			fromServer = self.ircd.servers[fromServer.nextClosest]
		self.ircd.broadcastToServers(fromServer, "JOIN", channel.name, prefix=user.uuid)

class JoinChannel(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params or not params[0]:
			user.sendSingleError("JoinCmd", irc.ERR_NEEDMOREPARAMS, "JOIN", "Not enough parameters")
			return None
		joiningChannels = params[0].split(",")
		chanKeys = params[1].split(",") if len(params) > 1 else []
		while len(chanKeys) < len(joiningChannels):
			chanKeys.append("")
		user.startErrorBatch("JoinCmd")
		removeIndices = []
		for index, chanName in enumerate(joiningChannels):
			if chanName[0] != "#":
				user.sendBatchedError("JoinCmd", irc.ERR_BADCHANMASK, chanName, "Bad channel mask")
				removeIndices.append(index)
		removeIndices.sort()
		removeIndices.reverse() # Put the indices to remove in reverse order so we don't have to finagle with them on removal
		for index in removeIndices:
			del joiningChannels[index]
			del chanKeys[index]
		if not joiningChannels:
			return None
		channels = []
		for chan in joiningChannels:
			try:
				channels.append(self.ircd.channels[chan] if chan in self.ircd.channels else IRCChannel(self.ircd, chan))
			except InvalidChannelNameError:
				user.sendBatchedError("JoinCmd", irc.ERR_BADCHANMASK, chanName, "Bad channel mask")
		return {
			"channels": channels,
			"keys": chanKeys
		}
	
	def affectedChannels(self, user, data):
		return data["channels"]
	
	def execute(self, user, data):
		for channel in data["channels"]:
			user.joinChannel(channel)
		return True

class ServerJoin(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if prefix not in self.ircd.users:
			if prefix in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		try:
			return {
				"user": self.ircd.users[prefix],
				"channel": self.ircd.channels[params[0]] if params[0] in self.ircd.channels else IRCChannel(self.ircd, params[0])
			}
		except ValueError:
			return None
	
	def execute(self, server, data):
		if "lostuser" not in data:
			data["user"].joinChannel(data["channel"], True, True)
		return True

class RemoteJoin(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		return {
			"prefix": prefix,
			"user": self.ircd.users[params[0]],
			"channel": params[1]
		}
	
	def execute(self, server, data):
		if "lostuser" in data:
			return True
		user = data["user"]
		chanName = data["channel"]
		if user.uuid[:3] == self.ircd.serverID:
			channel = self.ircd.channels[chanName] if chanName in self.ircd.channels else IRCChannel(self.ircd, chanName)
			user.joinChannel(channel, True)
		else:
			self.ircd.servers[user.uuid[:3]].sendMessage("RJOIN", user.uuid, chanName, prefix=data["prefix"])
		return True

joinCommand = JoinCommand()