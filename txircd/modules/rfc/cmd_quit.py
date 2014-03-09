from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class QuitCommand(ModuleData, Command):
    implements(IPlugin, IModuleData)
    
    name = "QuitCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("quitmessage", 10, self.sendQuitMessage),
                ("remotequitrequest", 10, self.sendRQuit),
                ("remotequit", 10, self.propagateQuit) ]
    
    def userCommands(self):
        return [ ("QUIT", 1, UserQuit(self.ircd)) ]
    
    def serverCommands(self):
        return [ ("QUIT", 1, ServerQuit(self.ircd)),
                ("RQUIT", 1, RemoteQuit(self.ircd)) ]
    
    def sendQuitMessage(self, user, reason, sendUserList):
        hostmask = user.hostmask()
        for destUser in sendUserList:
            destUser.sendMessage("QUIT", ":{}".format(reason), to=None, prefix=hostmask)
        del sendUserList[:]
    
    def sendRQuit(self, user, reason):
        self.ircd.servers[user.uuid[:3]].sendMessage("RQUIT", ":{}".format(reason), prefix=user.uuid)
        return True
    
    def propagateQuit(self, user, reason):
        fromServer = self.ircd.servers[user.uuid[:3]]
        while fromServer.nextClosest != self.ircd.serverID:
            fromServer = self.ircd.servers[fromServer.nextClosest]
        for server in self.ircd.servers.itervalues():
            if server != fromServer and server.nextClosest == self.ircd.serverID:
                server.sendMessage("QUIT", ":{}".format(reason), prefix=user.uuid)

class UserQuit(Command):
    implements(ICommand)
    
    forRegisteredUsers = None
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if not params or not params[0]:
            return {
                "reason": None
            }
        return {
            "reason": params[0][:self.ircd.config.getWithDefault("quit_msg_length", 255)]
        }
    
    def execute(self, user, data):
        if data["reason"] is None:
            user.disconnect("Client quit")
        else:
            user.disconnect("Quit: {}".format(data["reason"]))
        return True

class ServerQuit(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if prefix not in self.ircd.users:
            return None
        if len(params) != 1:
            return None
        return {
            "user": self.ircd.users[prefix],
            "reason": params[0]
        }
    
    def execute(self, server, data):
        data["user"].disconnect(data["reason"], True)
        return True

class RemoteQuit(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if prefix not in self.ircd.users:
            return None
        if len(params) != 1:
            return None
        return {
            "user": self.ircd.users[prefix],
            "reason": params[0]
        }
    
    def execute(self, server, data):
        user = data["user"]
        if user.uuid[:3] == self.ircd.serverID:
            user.disconnect(data["reason"])
            return True
        self.ircd.servers[user.uuid[:3]].sendMessage("RQUIT", ":{}".format(data["reason"]), prefix=user.uuid)

quitCommand = QuitCommand()