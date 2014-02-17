from twisted.words.protocols.irc import IRC

class IRCServer(IRC):
    def __init__(self, ircd, ip):
        self.ircd = ircd
        self.serverID = None
        self.name = None
        self.ip = ip
        self.remoteServers = {}
        self.cache = {}
    
    def handleCommand(self, command, prefix, params):
        if command not in self.ircd.serverCommands:
            self.transport.loseConnection() # If we receive a command we don't recognize, abort immediately to avoid a desync
            return
        handlers = self.ircd.serverCommands[command]
        data = None
        for handler in handlers:
            data = handler[0].parseParams(params)
            if data is not None:
                break
        if data is None:
            self.transport.loseConnection() # If we receive a command we can't parse, also abort immediately
            return
        for handler in handlers:
            if handler[0].execute(self, data):
                break
        else:
            self.transport.loseConnection() # Also abort connection if we can't process a command
            return
    
    def connectionLost(self, reason):
        del self.ircd.servers[self.serverID]
        del self.ircd.serverNames[self.name]
        # TODO: Disconnect remote users
    
    def register():
        if not self.serverID:
            return
        if not self.name:
            return
        self.ircd.servers[self.serverID] = self
        self.ircd.serverNames[self.name] = self.serverID