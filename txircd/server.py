from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.task import LoopingCall
from txircd.ircbase import IRCBase
from txircd.utils import now

class IRCServer(IRCBase):
	def __init__(self, ircd, ip, received):
		self.ircd = ircd
		self.serverID = None
		self.name = None
		self.description = None
		self.ip = ip
		self.nextClosest = self.ircd.serverID
		self.cache = {}
		self.bursted = None
		self.disconnectedDeferred = Deferred()
		self.receivedConnection = received
		self._pinger = LoopingCall(self._ping)
		self._registrationTimeoutTimer = reactor.callLater(self.ircd.config.get("server_registration_timeout", 10), self._timeoutRegistration)
	
	def handleCommand(self, command, params, prefix, tags):
		if command not in self.ircd.serverCommands:
			self.disconnect("Unknown command {}".format(command)) # If we receive a command we don't recognize, abort immediately to avoid a desync
			return
		handlers = self.ircd.serverCommands[command]
		data = None
		for handler in handlers:
			if self.bursted is False and handler[0].forRegistered:
				if "burst_queue" not in self.cache:
					self.cache["burst_queue"] = []
				self.cache["burst_queue"].append((command, prefix, params))
				return
			data = handler[0].parseParams(self, params, prefix, tags)
			if data is not None:
				break
		if data is None:
			self.disconnect("Failed to parse command {} from {} with prefix '{}' and parameters {!r}".format(command, prefix, prefix, params)) # If we receive a command we can't parse, also abort immediately
			return
		for handler in handlers:
			if handler[0].execute(self, data):
				break
		else:
			self.disconnect("Couldn't process command {} from {} with prefix '{}' and parameters {!r}".format(command, prefix, prefix, params)) # Also abort connection if we can't process a command
			return
	
	def endBurst(self):
		"""
		Called at the end of bursting.
		"""
		self.bursted = True
		if "burst_queue" in self.cache:
			for command, prefix, params in self.cache["burst_queue"]:
				self.handleCommand(command, prefix, params)
				if self.bursted is None:
					break # Something failed to process, so we disconnected
			del self.cache["burst_queue"]
	
	def connectionLost(self, reason):
		if self.serverID in self.ircd.servers:
			self.disconnect("Connection reset")
		self.disconnectedDeferred.callback(None)
	
	def disconnect(self, reason, netsplitQuitMsg = None):
		"""
		Disconnects the server.
		"""
		self.ircd.log.warn("Disconnecting server {server}: {reason}", server=self.name, reason=reason)
		self.ircd.runActionStandard("serverquit", self, reason)
		if self.bursted:
			if netsplitQuitMsg is None:
				netsplitQuitMsg = "{} {}".format(self.ircd.servers[self.nextClosest].name if self.nextClosest in self.ircd.servers else self.ircd.name, self.name)
			allUsers = self.ircd.users.values()
			for user in allUsers:
				if user.uuid[:3] == self.serverID:
					user.disconnect(netsplitQuitMsg, True)
			allServers = self.ircd.servers.values()
			for server in allServers:
				if server.nextClosest == self.serverID:
					server.disconnect(reason, netsplitQuitMsg)
			self.ircd.recentlyQuitServers[self.serverID] = now()
			del self.ircd.servers[self.serverID]
			del self.ircd.serverNames[self.name]
		self.bursted = None
		if self._pinger.running:
			self._pinger.stop()
		if self._registrationTimeoutTimer.active():
			self._registrationTimeoutTimer.cancel()
		self._endConnection()
	
	def _endConnection(self):
		self.transport.loseConnection()
	
	def _timeoutRegistration(self):
		if self.serverID and self.name:
			self._pinger.start(self.ircd.config.get("server_ping_frequency", 60))
			return
		self.ircd.log.info("Disconnecting unregistered server")
		self.disconnect("Registration timeout")
	
	def _ping(self):
		self.ircd.runActionStandard("pingserver", self)
	
	def register(self):
		"""
		Marks the server as registered. Should be called once after capability
		negotiation.
		"""
		if not self.serverID:
			return
		if not self.name:
			return
		self.ircd.servers[self.serverID] = self
		self.ircd.serverNames[self.name] = self.serverID
		self.ircd.runActionStandard("serverconnect", self)
		if self.nextClosest != self.ircd.serverID:
			self.bursted = True # Indicate that this server is fully connected and synced NOW since it's a remote server and we've either already gotten or are about to get all the interesting tidbits

class RemoteServer(IRCServer):
	def __init__(self, ircd, ip):
		IRCServer.__init__(self, ircd, ip, True)
		self._registrationTimeoutTimer.cancel()
	
	def sendMessage(self, command, *params, **kw):
		"""
		Sends a message to the locally-connected server that will route to the
		remote server.
		Messages sent this way should have some information in the contents so
		that they can be propagated in the correct direction.
		"""
		target = self
		while target.nextClosest != self.ircd.serverID:
			target = self.ircd.servers[target.nextClosest]
		target.sendMessage(command, *params, **kw)
	
	def _endConnection(self):
		pass