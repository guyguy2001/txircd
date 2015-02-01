from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from twisted.python import log
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import durationToSeconds
from zope.interface import implements
import logging

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
				log.msg("Failed to autoconnect server {}: probably broken config".format(serverName), logLevel=logging.WARNING)
			else:
				d.addErrback(lambda result: log.msg("Failed to autoconnect server {}: {}".format(serverName, result.getErrorMessage()), logLevel=logging.ERROR))

autoconnect = ServerAutoconnect()