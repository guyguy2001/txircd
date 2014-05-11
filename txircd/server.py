from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.task import LoopingCall
from twisted.words.protocols.irc import IRC

class IRCServer(IRC):
    def __init__(self, ircd, ip):
        self.ircd = ircd
        self.serverID = None
        self.name = None
        self.description = None
        self.ip = ip
        self.remoteServers = {}
        self.nextClosest = self.ircd.serverID
        self.cache = {}
        self.disconnectedDeferred = Deferred()
        self._pinger = LoopingCall(self._ping)
        self._registrationTimeoutTimer = reactor.callLater(self.ircd.config.getWithDefault("server_registration_timeout", 10), self._timeoutRegistration)
    
    def handleCommand(self, command, prefix, params):
        if command not in self.ircd.serverCommands:
            self.transport.loseConnection() # If we receive a command we don't recognize, abort immediately to avoid a desync
            return
        handlers = self.ircd.serverCommands[command]
        data = None
        for handler in handlers:
            data = handler[0].parseParams(self, params, prefix, {})
            if data is not None:
                break
        if data is None:
            self.transport.loseConnection() # If we receive a command we can't parse, also abort immediately
            return
        for handler in handlers:
            if handler[0].execute(self, data):
                break
        else:
            self.disconnect("Desync: Couldn't process command") # Also abort connection if we can't process a command
            return
    
    def connectionLost(self, reason):
        if self.serverID in self.ircd.servers:
            self.disconnect("Connection reset")
        self.disconnectedDeferred.callback(None)
    
    def disconnect(self, reason):
        self.ircd.runActionStandard("serverquit", self, reason)
        del self.ircd.servers[self.serverID]
        del self.ircd.serverNames[self.name]
        netsplitQuitMsg = "{} {}".format(self.ircd.servers[self.nextClosest].name if self.nextClosest in self.ircd.servers else self.ircd.name, self.name)
        allUsers = self.ircd.users.values()
        for user in allUsers:
            if user.uuid[:3] == self.serverID or user.uuid[:3] in self.remoteServers:
                user.disconnect(netsplitQuitMsg)
        self._endConnection()
    
    def _endConnection(self):
        self.transport.loseConnection()
    
    def _timeoutRegistration(self):
        if self.serverID and self.name:
            self._pinger.start(self.ircd.config.getWithDefault("server_ping_frequency", 60))
            return
        self.disconnect("Registration timeout")
    
    def _ping(self):
        self.ircd.runActionStandard("pingserver", self)
    
    def register():
        if not self.serverID:
            return
        if not self.name:
            return
        self.ircd.servers[self.serverID] = self
        self.ircd.serverNames[self.name] = self.serverID

class RemoteServer(IRCServer):
    def __init__(self, ircd, ip):
        IRCServer.__init__(self, ircd, ip)
        self._registrationTimeoutTimer.cancel()
    
    def sendMessage(self, command, *params, **kw):
        target = self
        while target.nextClosest != self.ircd.serverID:
            target = self.ircd.servers[target.nextClosest]
        target.sendMessage(command, *params, **kw)
    
    def _endConnection(self):
        pass