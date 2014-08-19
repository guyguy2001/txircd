from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import now
from zope.interface import implements

class PingPong(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "PingPong"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("pinguser", 10, self.pingUser),
                ("pingserver", 10, self.pingServer) ]
    
    def userCommands(self):
        return [ ("PING", 1, UserPing()),
                ("PONG", 1, UserPong()) ]
    
    def serverCommands(self):
        return [ ("PING", 1, ServerPing(self.ircd)),
                ("PONG", 1, ServerPong(self.ircd)) ]
    
    def pingUser(self, user):
        if "pingtime" not in user.cache or "pongtime" not in user.cache:
            user.cache["pingtime"] = now()
            user.cache["pongtime"] = now()
        if user.cache["pongtime"] < user.cache["pingtime"]:
            user.disconnect("Ping timeout")
            return
        if user.idleSince > user.cache["pongtime"]:
            user.cache["pingtime"] = now()
            user.cache["pongtime"] = now()
            return
        user.sendMessage("PING", ":{}".format(self.ircd.name), to=None, prefix=None)
        user.cache["pingtime"] = now()
    
    def pingServer(self, server):
        if "pingtime" not in server.cache or "pongtime" not in server.cache:
            server.cache["pingtime"] = now()
            server.cache["pongtime"] = now()
        if server.cache["pongtime"] < server.cache["pingtime"]:
            server.disconnect("Ping timeout")
            return
        server.sendMessage("PING", self.ircd.serverID, server.serverID, prefix=self.ircd.serverID)
        server.cache["pingtime"] = now()

class UserPing(Command):
    implements(ICommand)
    
    resetsIdleTime = False
    forRegisteredUsers = None
    
    def parseParams(self, user, params, prefix, tags):
        if not params:
            user.sendSingleError("PingCmd", irc.ERR_NEEDMOREPARAMS, "PING", ":Not enough parameters")
            return None
        return {
            "data": params[0]
        }
    
    def execute(self, user, data):
        user.sendMessage("PONG", ":{}".format(data["data"]), to=self.ircd.name)
        return True

class UserPong(Command):
    implements(ICommand)
    
    resetsIdleTime = False
    forRegisteredUsers = None
    
    def parseParams(self, user, params, prefix, tags):
        if not params:
            user.sendSingleError("PongCmd", irc.ERR_NEEDMOREPARAMS, "PONG", ":Not enough parameters")
            return None
        return {
            "data": params[0]
        }
    
    def execute(self, user, data):
        user.cache["pongtime"] = now()
        return True

class ServerPing(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2:
            return None
        if params[0] not in self.ircd.servers:
            return None
        if params[1] != self.ircd.serverID and params[1] not in self.ircd.servers:
            return None
        return {
            "prefix": prefix,
            "source": params[0],
            "dest": params[1]
        }
    
    def execute(self, server, data):
        if data["dest"] == self.ircd.serverID:
            server.sendMessage("PONG", data["dest"], data["source"], prefix=data["prefix"])
            return True
        self.ircd.servers[data["dest"]].sendMessage("PING", data["source"], data["dest"], prefix=data["prefix"])
        return True

class ServerPong(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2:
            return None
        if params[0] not in self.ircd.servers:
            return None
        if params[1] != self.ircd.serverID and params[1] not in self.ircd.servers:
            return None
        return {
            "prefix": prefix,
            "source": params[0],
            "dest": params[1]
        }
    
    def execute(self, server, data):
        if data["dest"] == self.ircd.serverID:
            self.ircd.servers[data["source"]].cache["lastpong"] = now()
            return True
        self.ircd.servers[data["dest"]].sendMessage("PONG", data["source"], data["dest"], prefix=data["prefix"])
        return True

pingpong = PingPong()