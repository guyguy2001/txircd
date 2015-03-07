from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import timestamp
from zope.interface import implements
from datetime import datetime

class ServerMetadata(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerMetadata"
	core = True
	
	def actions(self):
		return [ ("usermetadataupdate", 10, self.propagateUserMetadata),
				("channelmetadataupdate", 10, self.propagateChannelMetadata) ]
	
	def serverCommands(self):
		return [ ("METADATA", 1, self) ]
	
	def propagateMetadata(self, targetID, targetTime, namespace, key, value, fromServer):
		serverPrefix = fromServer.serverID if fromServer else self.ircd.serverID
		if value is None:
			self.ircd.broadcastToServers(fromServer, "METADATA", targetID, targetTime, namespace, key, prefix=serverPrefix)
		else:
			self.ircd.broadcastToServers(fromServer, "METADATA", targetID, targetTime, namespace, key, value, prefix=serverPrefix)
	
	def propagateUserMetadata(self, user, namespace, key, oldValue, value, fromServer):
		self.propagateMetadata(user.uuid, str(timestamp(user.connectedSince)), namespace, key, value, fromServer)
	
	def propagateChannelMetadata(self, channel, namespace, key, oldValue, value, fromServer):
		self.propagateMetadata(channel.name, str(timestamp(channel.existedSince)), namespace, key, value, fromServer)
	
	def clearMetadata(self, target, server):
		metadataToClear = target.metadata.copy()
		for namespace, data in metadataToClear.iteritems():
			for key in data.iterkeys():
				target.setMetadata(namespace, key, None, server)
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 4 and len(params) != 5:
			return None
		data = {}
		if params[0] in self.ircd.users:
			data["user"] = self.ircd.users[params[0]]
		elif params[0] in self.ircd.channels:
			data["channel"] = self.ircd.channels[params[0]]
		else:
			return None
		if params[2] not in ("server", "user", "client", "ext", "private"):
			return None
		try:
			data["time"] = datetime.utcfromtimestamp(int(params[1]))
		except ValueError:
			return None
		data["namespace"] = params[2]
		data["key"] = params[3]
		if len(params) == 5:
			data["value"] = params[4]
		return data
	
	def execute(self, server, data):
		if "user" in data:
			target = data["user"]
			if data["time"] > target.connectedSince:
				self.clearMetadata(target, server)
				return True
		else:
			target = data["channel"]
			if data["time"] > target.existedSince:
				self.clearMetadata(target, server)
				return True
		if "value" in data:
			value = data["value"]
		else:
			value = None
		target.setMetadata(data["namespace"], data["key"], value, server)
		return True

serverMetadata = ServerMetadata()