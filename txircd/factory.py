from twisted.internet.protocol import Factory
from txircd.server import IRCServer
from txircd.user import IRCUser

class UserFactory(Factory):
    protocol = IRCUser

class ServerFactory(Factory):
    protocol = IRCServer