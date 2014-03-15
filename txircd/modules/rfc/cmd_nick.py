from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ircLower, isValidNick, timestamp
from zope.interface import implements
from datetime import datetime

class NickCommand(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "NickCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("changenickmessage", 1, self.sendNickMessage),
                ("remotenickrequest", 1, self.forwardNickRequest),
                ("changenick", 1, self.broadcastNickChange),
                ("remotechangenick", 1, self.propagateNickChange) ]
    
    def userCommands(self):
        return [ ("NICK", 1, NickUserCommand(self.ircd)) ]
    
    def serverCommands(self):
        return [ ("NICK", 1, NickServerCommand(self.ircd)),
                ("CHGNICK", 1, ChgNickServerCommand(self.ircd)) ]
    
    def sendNickMessage(self, userShowList, user, oldNick):
        prefix = "{}!{}@{}".format(oldNick, user.ident, user.host)
        for targetUser in userShowList:
            targetUser.sendMessage("NICK", to=user.nick, prefix=prefix)
        del userShowList[:]
    
    def forwardNickRequest(self, user, newNick):
        self.ircd.servers[user.uuid[:3]].sendMessage("CHGNICK", user.uuid, newNick, prefix=self.ircd.serverID)
        return True
    
    def broadcastNickChange(self, user, oldNick):
        nickTS = timestamp(user.nickSince)
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID:
                server.sendMessage("NICK", nickTS, user.nick, prefix=user.uuid)
    
    def propagateNickChange(self, user, oldNick):
        nickTS = timestamp(user.nickSince)
        fromServer = self.ircd.servers[user.uuid[:3]]
        while fromServer.nextClosest != self.ircd.serverID:
            fromServer = self.ircd.servers[fromServer.nextClosest]
        for server in self.ircd.servers.itervalues():
            if server != fromServer and server.nextClosest == self.ircd.serverID:
                server.sendMessage("NICK", nickTS, user.nick, prefix=user.uuid)

class NickUserCommand(Command):
    implements(ICommand)
    
    forRegisteredUsers = None
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if not params or not params[0]:
            user.sendMessage(irc.ERR_NEEDMOREPARAMS, "NICK", ":Not enough parameters")
            return None
        if not isValidNick(params[0]):
            user.sendMessage(irc.ERR_ERRONEUSNICKNAME, params[0], ":Erroneous nickname")
            return None
        if params[0] in self.ircd.userNicks:
            otherUserID = self.ircd.userNicks[params[0]]
            if user.uuid != otherUserID:
                user.sendMessage(irc.ERR_NICKNAMEINUSE, nick, ":Nickname is already in use")
                return None
        return {
            "nick": params[0]
        }
    
    def execute(self, user, data):
        user.changeNick(data["nick"])
        if not user.isRegistered():
            user.register("NICK")
        return True

class NickServerCommand(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2:
            return None
        if prefix not in self.ircd.users:
            self.disconnect("Desync: User list")
            return None
        user = self.ircd.users[prefix]
        try:
            time = datetime.utcfromtimestamp(params[0])
        except ValueError:
            return None
        if params[1] in self.ircd.userNicks:
            localUser = self.ircd.users[self.ircd.userNicks[params[1]]]
            if localUser != user:
                if localUser.localOnly:
                    if self.ircd.runActionUntilTrue("localnickcollision"):
                        return {
                            "user": user,
                            "time": time,
                            "nick": params[1]
                        }
                    return None
                self.disconnect("Desync: User data (nicknames)")
                return None
        return {
            "user": user,
            "time": time,
            "nick": params[1]
        }
    
    def execute(self, server, data):
        user = data["user"]
        user.changeNick(data["nick"], True)
        user.nickSince = data["time"]
        return True

class ChgNickServerCommand(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2:
            return None
        if params[0] not in self.ircd.users:
            return None
        return {
            "prefix": prefix,
            "user": params[0],
            "nick": params[1]
        }
    
    def execute(self, server, data):
        user = self.ircd.users[data["user"]]
        if user.uuid[:3] == self.ircd.serverID:
            user.changeNick(data["nick"])
        else:
            self.ircd.servers[user.uuid[:3]].sendMessage("CHGNICK", user.uuid, data["nick"], prefix=data["prefix"])
        return True

cmd_nick = NickCommand()