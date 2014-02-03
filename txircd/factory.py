from twisted.internet.protocol import Factory
from txircd.user import IRCUser

class UserFactory(Factory):
    protocol = IRCUser