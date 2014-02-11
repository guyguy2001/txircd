from twisted.words.protocols.irc import IRC
from socket import gethostbyaddr, herror

class IRCUser(IRC):
    def __init__(self, ircd, ip):
        self.ircd = ircd
        self.uuid = ircd.createUUID()
        self.nick = None
        self.ident = None
        try:
            host = gethostbyaddr(ip)[0]
        except herror:
            host = ip
        self.host = host
        self.realhost = host
        self.ip = ip
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