from twisted.internet.protocol import Factory
from txircd.server import IRCServer
from txircd.user import IRCUser

class UserFactory(Factory):
    protocol = IRCUser
    
    def __init__(self, ircd):
        self.ircd = ircd

class ServerListenFactory(Factory):
    protocol = IRCServer
    
    def __init__(self, ircd):
        self.ircd = ircd