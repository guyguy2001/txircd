from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import timestampStringFromTime
from zope.interface import implements
from datetime import datetime

class ServerMetadata(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerMetadata"
	core = True
	burstQueuePriority = 70
	
	def actions(self):
		return [ ("usermetadataupdate", 10, self.propagateUserMetadata),
		         ("channelmetadataupdate", 10, self.propagateChannelMetadata),
		         ("welcome", 10, self.propagateAllUserMetadata) ]
	
	def serverCommands(self):
		return [ ("METADATA", 1, self) ]
	
	def propagateMetadata(self, targetID, targetTime, key, value, fromServer):
		serverPrefix = fromServer.serverID if fromServer else self.ircd.serverID
		if value is None:
			self.ircd.broadcastToServers(fromServer, "METADATA", targetID, targetTime, key, prefix=serverPrefix)
		else:
			self.ircd.broadcastToServers(fromServer, "METADATA", targetID, targetTime, key, value, prefix=serverPrefix)
	
	def propagateUserMetadata(self, user, key, oldValue, value, fromServer):
		if user.isRegistered():
			self.propagateMetadata(user.uuid, timestampStringFromTime(user.connectedSince), key, value, fromServer)
	
	def propagateChannelMetadata(self, channel, key, oldValue, value, fromServer):
		self.propagateMetadata(channel.name, timestampStringFromTime(channel.existedSince), key, value, fromServer)
	
	def propagateAllUserMetadata(self, user):
		metadataList = user.metadataList()
		userID = user.uuid
		metadataTime = timestampStringFromTime(user.connectedSince)
		for key, value in metadataList:
			self.propagateMetadata(userID, metadataTime, key, value, None)
	
	def clearMetadata(self, target, server):
		metadataToClear = target.metadataList()
		for key, value in metadataToClear:
			target.setMetadata(key, None, server)
	
	def parseParams(self, server, params, prefix, tags):
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
	
	def execute(self, server, data):
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