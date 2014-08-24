from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import isValidNick, timestamp
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
                ("changenick", 1, self.broadcastNickChange),
                ("remotechangenick", 1, self.broadcastNickChange) ]
    
    def userCommands(self):
        return [ ("NICK", 1, NickUserCommand(self.ircd)) ]
    
    def serverCommands(self):
        return [ ("NICK", 1, NickServerCommand(self.ircd)) ]
    
    def sendNickMessage(self, userShowList, user, oldNick):
        def transformUser(sayingUser):
            return "{}!{}@{}".format(oldNick, sayingUser.ident, sayingUser.host)
        for targetUser in userShowList:
            targetUser.sendMessage("NICK", to=user.nick, sourceuser=user, usertransform=transformUser)
        del userShowList[:]
    
    def broadcastNickChange(self, user, oldNick, fromServer):
        nickTS = str(timestamp(user.nickSince))
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID and server != fromServer:
                server.sendMessage("NICK", nickTS, user.nick, prefix=user.uuid)

class NickUserCommand(Command):
    implements(ICommand)
    
    forRegistered = None
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if not params or not params[0]:
            user.sendSingleError("NickCmd", irc.ERR_NEEDMOREPARAMS, "NICK", ":Not enough parameters")
            return None
        if not isValidNick(params[0]):
            user.sendSingleError("NickCmd", irc.ERR_ERRONEUSNICKNAME, params[0], ":Erroneous nickname")
            return None
        if params[0] in self.ircd.userNicks:
            otherUserID = self.ircd.userNicks[params[0]]
            if user.uuid != otherUserID:
                user.sendSingleError("NickCmd", irc.ERR_NICKNAMEINUSE, params[0], ":Nickname is already in use")
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
            return None
        user = self.ircd.users[prefix]
        try:
            time = datetime.utcfromtimestamp(int(params[0]))
        except ValueError:
            return None
        if params[1] in self.ircd.userNicks:
            localUser = self.ircd.users[self.ircd.userNicks[params[1]]]
            if localUser != user:
                if localUser.localOnly:
                    allowChange = self.ircd.runActionUntilValue("localnickcollision", localUser, user, users=[localUser, user])
                    if allowChange:
                        return {
                            "user": user,
                            "time": time,
                            "nick": params[1]
                        }
                    if allowChange is False:
                        return {
                            "user": user,
                            "time": time,
                            "nick": None
                        }
                    return None
                return None
        return {
            "user": user,
            "time": time,
            "nick": params[1]
        }
    
    def execute(self, server, data):
        user = data["user"]
        newNick = data["nick"]
        if not newNick:
            return True # Handled collision by not changing the user's nick
        if newNick in self.ircd.userNicks:
            user.changeNick(user.uuid)
            return True
        user.changeNick(data["nick"], server)
        user.nickSince = data["time"]
        return True

cmd_nick = NickCommand()