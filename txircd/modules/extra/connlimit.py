from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class ConnectionLimit(ModuleData):
	implements(IPlugin, IModuleData)

	name = "ConnectionLimit"
	peerConnections = {}

	def actions(self):
		return [ ("userconnect", 100, self.handleLocalConnect),
				("remoteregister", 100, self.handleRemoteConnect),
				("quit", 100, self.handleDisconnect),
				("remotequit", 100, self.handleDisconnect) ]

	def handleLocalConnect(self, user, *params):
		ip = user.ip
		if self.addToConnections(ip) and self.peerConnections[ip] > self.ircd.config.get("connlimit_globmax", 3):
			self.ircd.log.info("Connection limit reached from {ip}", ip=ip)
			user.disconnect("No more connections allowed from your IP ({})".format(ip))
			return None
		return True

	def handleRemoteConnect(self, user, *params):
		self.addToConnections(user.ip)

	def handleDisconnect(self, user, *params):
		ip = user.ip
		if ip in self.peerConnections:
			self.peerConnections[ip] -= 1
			if self.peerConnections[ip] < 1:
				del self.peerConnections[ip]

	def addToConnections(self, ip):
		if ip in self.ircd.config.get("connlimit_whitelist", []):
			return False
		if ip in self.peerConnections:
			self.peerConnections[ip] += 1
		else:
			self.peerConnections[ip] = 1
		return True

	def load(self):
		for user in self.ircd.users:
			self.addToConnections(user.ip)

connLimit = ConnectionLimit()