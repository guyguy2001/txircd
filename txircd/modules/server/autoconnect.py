from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from twisted.python import log
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements
import logging

class ServerAutoconnect(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "ServerAutoconnect"
    core = True
    connector = None
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def load(self):
        self.connector = LoopingCall(self.runConnections)
        self.connector.start(self.ircd.config.getWithDefault("autoconnect_period", 60), False)
    
    def unload(self):
        self.connector.stop()
    
    def runConnections(self):
        autoconnectServers = self.ircd.config.getWithDefault("autoconnect", [])
        for serverName in autoconnectServers:
            if serverName in self.ircd.serverNames:
                continue
            d = self.ircd.connectServer(serverName)
            if not d:
                log.msg("Failed to autoconnect server {}: probably broken config".format(serverName), logLevel=logging.WARNING)
            d.addErrback(lambda result: log.msg("Failed to autoconnect server {}: {}".format(result.getErrorMessage()), logLevel=logging.ERROR))

autoconnect = ServerAutoconnect()