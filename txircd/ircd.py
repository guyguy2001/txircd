from twisted.application.service import Service
from txircd.config import Config

class IRCd(Service):
    def __init__(self, configFileName):
        self.config = Config(configFileName)
    
    def startService(self):
        pass # There'll definitely be some stuff here
    
    def stopService(self):
        pass # Here, too