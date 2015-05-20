from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import durationToSeconds
from zope.interface import implements

class ServerAutoconnect(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ServerAutoconnect"
	core = True
	connector = None
	
	def load(self):
		self.connector = LoopingCall(self.runConnections)
		self.connector.start(durationToSeconds(self.ircd.config.get("autoconnect_period", 60)), False)
	
	def unload(self):
		if self.connector.running:
			self.connector.stop()
	
	def rehash(self):
		if self.connector.running:
			self.connector.stop()
		self.connector.start(durationToSeconds(self.ircd.config.get("autoconnect_period", 60)), False)
	
	def runConnections(self):
		autoconnectServers = self.ircd.config.get("autoconnect", [])
		for serverName in autoconnectServers:
			if serverName in self.ircd.serverNames:
				continue
			d = self.ircd.connectServer(serverName)
			if not d:
				self.ircd.log.warn("Failed to autoconnect server {serverName}: probably broken config", serverName=serverName)
			else:
				d.addErrback(lambda result: self.ircd.log.error("Failed to autoconnect server {serverName}: {err.getErrorMessage()}", serverName=serverName, err=result))

autoconnect = ServerAutoconnect()