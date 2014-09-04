from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class Wallops(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "Wallops"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def userCommands(self):
        return [ ("WALLOPS", 1, UserWallops(self.ircd)) ]
    
    def serverCommands(self):
        return [ ("WALLOPS", 1, ServerWallops(self.ircd)) ]
    
    def actions(self):
        return [ ("commandpermission-WALLOPS", 1, self.canWallops) ]
    
    def userModes(self):
        return [ ("w", ModeType.NoParam, self) ]
    
    def canWallops(self, user, command, data):
        if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-wallops", users=[user]):
            user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - no oper permission to run command WALLOPS")
            return False
        return None

class UserWallops(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if not params:
            user.sendSingleError("WallopsCmd", irc.ERR_NEEDMOREPARAMS, "WALLOPS", ":Not enough parameters")
            return None
        return {
            "message": " ".join(params)
        }
    
    def execute(self, user, data):
        message = ":{}".format(data["message"])
        for u in self.ircd.users.itervalues():
            if u.uuid[:3] == self.ircd.serverID and "w" in u.modes:
                u.sendMessage("WALLOPS", message, sourceuser=user, to=None)
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID:
                server.sendMessage("WALLOPS", message, prefix=user.uuid)
        return True

class ServerWallops(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 1:
            return None
        if prefix not in self.ircd.users:
            return None
        return {
            "message": params[0],
            "from": self.ircd.users[prefix]
        }
    
    def execute(self, server, data):
        fromUser = data["from"]
        message = ":{}".format(data["message"])
        for user in self.ircd.users.itervalues():
            if user.uuid[:3] == self.ircd.serverID and "w" in user.modes:
                user.sendMessage("WALLOPS", message, sourceuser=fromUser, to=None)
        for s in self.ircd.servers.itervalues():
            if s.nextClosest == self.ircd.serverID and s != server:
                s.sendMessage("WALLOPS", message, prefix=fromUser.uuid)
        return True

wallops = Wallops()