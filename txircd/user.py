from twisted.words.protocols import irc
from txircd.utils import now
from socket import gethostbyaddr, herror

irc.ERR_ALREADYREGISTERED = "462"

class IRCUser(irc.IRC):
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
        self.idleSince = now()
        self._registered = 2
    
    def connectionMade(self):
        if "user_connect" in self.ircd.actions:
            for action in self.ircd.actions["user_connect"]:
                if not action[0](self):
                    self.transport.loseConnection()
                    return
    
    def dataReceived(self, data):
        if "user_recvdata" in self.ircd.actions:
            for action in self.ircd.actions["user_recvdata"]:
                action[0](self, line)
        irc.IRC.dataReceived(self, data)
    
    def sendLine(self, line):
        if "user_senddata" in self.ircd.actions:
            for action in self.ircd.actions["user_senddata"]:
                action[0](self, line)
        irc.IRC.sendLine(self, line)
    
    def sendMessage(self, command, *args, **kw):
        if "prefix" not in kw:
            kw["prefix"] = self.ircd.name
        if kw["prefix"] is None:
            del kw["prefix"]
        if "to" not in kw:
            kw["to"] = self.nickname if self.nickname else "*"
        if kw["to"] is None:
            del kw["to"]
        irc.IRC.sendMessage(self, command, *args, **kw)
    
    def handleCommand(self, command, prefix, params):
        if command in self.ircd.userCommands:
            handlers = self.ircd.userCommands[command]
            if not handlers:
                return
            data = None
            spewRegWarning = True
            for handler in handlers:
                if handler[0].forRegisteredUsers is not None:
                    if (handler[0].forRegisteredUsers is True and self._registered > 0) or (handler[0].forRegisteredUsers is False and self._registered == 0):
                        continue
                spewRegWarning = False
                data = handler[0].parseParams()
                if data is not None:
                    break
            if data is None:
                if spewRegWarning:
                    if self._registered == 0:
                        self.sendMessage(irc.ERR_ALREADYREGISTERED, ":You may not reregister")
                    else:
                        self.sendMessage(irc.ERR_NOTREGISTERED, command, ":You have not registered")
                return
            actionName = "commandpermission-{}".format(command)
            if actionName in self.ircd.actions:
                permissionCount = 0
                for action in self.ircd.actions[actionName]:
                    result = action[0](self, command, data)
                    if result is True:
                        permissionCount += 1
                    elif result is False:
                        permissionCount -= 1
                    elif result is not None:
                        permissionCount += result
                if permissionCount < 0:
                    return
            actionName = "commandmodify-{}".format(command)
            if actionName in self.ircd.actions:
                for action in self.ircd.actions[actionName]:
                    newData = action[0](self, command, data)
                    if newData is not None:
                        data = newData
            for handler in handlers:
                if handler[0].execute(self, data):
                    if handler[0].resetsIdleTime:
                        self.idleSince = now()
                    break # If the command executor returns True, it was handled
            else:
                return # Don't process commandextra if it wasn't handled
            actionName = "commandextra-{}".format(command)
            if actionName in self.ircd.actions:
                for action in self.ircd.actions[actionName]:
                    action[0](self, command, data)
        else:
            self.sendMessage(irc.ERR_UNKNOWNCOMMAND, command, ":Unknown command")