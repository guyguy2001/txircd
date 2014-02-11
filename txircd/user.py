from twisted.words.protocols.irc import IRC

class IRCUser(IRC):
    def __init__(self, ircd):
        self.ircd = ircd
        self.nick = None
        self.ident = None
        self.host = None
        self.realhost = None
        self.gecos = None
        self.metadata = {
            "server": {},
            "user": {},
            "client": {},
            "ext": {},
            "private": {}
        }
        self.cache = {}
        self.channels = []
        self.modes = {}
        self.registered = 2