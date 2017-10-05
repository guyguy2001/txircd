from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import durationToSeconds
from zope.interface import implementer
from typing import Any, Dict, Optional

@implementer(IPlugin, IModuleData)
class ServerAutoconnect(ModuleData):
	name = "ServerAutoconnect"
	core = True
	connector = None
	
	def load(self) -> None:
		self.connector = LoopingCall(self.runConnections)
		self.connector.start(durationToSeconds(self.ircd.config.get("autoconnect_period", 60)), False)
	
	def unload(self) -> Optional["Deferred"]:
		if self.connector.running:
			self.connector.stop()
	
	def rehash(self) -> None:
		if self.connector.running:
			self.connector.stop()
		self.connector.start(durationToSeconds(self.ircd.config.get("autoconnect_period", 60)), False)

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "autoconnect_period" in config and (not isinstance(config["autoconnect_period"], int) or config["autoconnect_period"] < 0):
			raise ConfigValidationError("autoconnect_period", "invalid number")
		if "autoconnect" in config:
			if not isinstance(config["autoconnect"], list):
				raise ConfigValidationError("autoconnect", "value must be a list")
			for server in config["autoconnect"]:
				if not isinstance(server, str):
					raise ConfigValidationError("autoconnect", "every entry must be a string")

	def runConnections(self) -> None:
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