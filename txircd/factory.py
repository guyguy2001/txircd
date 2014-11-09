from twisted.internet.protocol import ClientFactory, Factory
from txircd.server import IRCServer
from txircd.user import IRCUser
from txircd.utils import unmapIPv4

class UserFactory(Factory):
    protocol = IRCUser
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def buildProtocol(self, addr):
        return self.protocol(self.ircd, unmapIPv4(addr.host))

class ServerListenFactory(Factory):
    protocol = IRCServer
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def buildProtocol(self, addr):
        return self.protocol(self.ircd, unmapIPv4(addr.host), True)

class ServerConnectFactory(ClientFactory):
    protocol = IRCServer
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def buildProtocol(self, addr):
        return self.protocol(self.ircd, unmapIPv4(addr.host), False)