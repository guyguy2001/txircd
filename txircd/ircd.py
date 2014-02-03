from twisted.application.service import Service
from twisted.internet.endpoints import serverFromString
from twisted.python import log
from txircd.config import Config
from txircd.factory import ClientFactory
from txircd.utils import unescapeEndpointDescription
import logging

class IRCd(Service):
    def __init__(self, configFileName):
        self.config = Config(configFileName)
        self.boundPorts = {}
    
    def startService(self):
        for bindDesc in self.config["bind_client"]:
            try:
                endpoint = serverFromString(unescapeEndpointDescription(bindDesc))
            except ValueError as e:
                log.msg(str(e), logLevel=logging.ERROR)
                continue
            listenDeferred = endpoint.listen(UserFactory)
            listenDeferred.addCallback(self._savePort, bindDesc)
            listenDeferred.addErrback(self._logNotBound, bindDesc)
    
    def stopService(self):
        pass # Here, too
    
    def _savePort(self, port, desc):
        self.boundPorts[desc] = port
    
    def _logNotBound(self, err, desc):
        log.msg("Could not bind '{}': {}".format(desc, err), logLevel=logging.ERROR)