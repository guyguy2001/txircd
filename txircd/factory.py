from twisted.internet.protocol import Factory
from txircd.server import IRCServer
from txircd.user import IRCUser
from txircd.utils import unmapIPv4

class UserFactory(Factory):
    protocol = IRCUser
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def buildProtocol(self, addr):
        try:
            return protocol(self.ircd, unmapIPv4(addr.host))
        except DenyConnection:
            return None

class ServerListenFactory(Factory):
    protocol = IRCServer
    
    def __init__(self, ircd):
        self.ircd = ircd

class DenyConnection(Exception):
    pass