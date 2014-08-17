from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.RPL_ADMINLOC1 = "257"
irc.RPL_ADMINLOC2 = "258"

class AdminCommand(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "AdminCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("sendremoteusermessage-256", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ADMINME, *params, **kw)),
                ("sendremoteusermessage-257", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ADMINLOC1, *params, **kw)),
                ("sendremoteusermessage-258", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ADMINLOC2, *params, **kw)),
                ("sendremoteusermessage-259", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ADMINEMAIL, *params, **kw)) ]
    
    def userCommands(self):
        return [ ("ADMIN", 1, UserAdmin(self.ircd, self.sendAdminData)) ]
    
    def serverCommands(self):
        return [ ("ADMINREQ", 1, ServerAdmin(self.ircd, self.sendAdminData)) ]
    
    def sendAdminData(self, user, serverName):
        user.sendMessage(irc.RPL_ADMINME, serverName, ":Administrative info for {}".format(serverName))
        try:
            adminData = self.ircd.config["admin_server"]
        except KeyError:
            adminData = ""
        if not adminData: # If the line is blank, let's provide a default value
            adminData = "This server has no admins. Anarchy!"
        user.sendMessage(irc.RPL_ADMINLOC1, ":{}".format(adminData))
        try:
            adminData = self.ircd.config["admin_admin"]
        except KeyError:
            adminData = ""
        if not adminData:
            adminData = "Nobody configured the second line of this."
        user.sendMessage(irc.RPL_ADMINLOC2, ":{}".format(adminData))
        try:
            adminEmail = self.ircd.config["admin_email"]
        except KeyError:
            adminEmail = ""
        if not adminEmail:
            adminEmail = "No Admin <anarchy@example.com>"
        user.sendMessage(irc.RPL_ADMINEMAIL, ":{}".format(adminEmail))
    
    def pushMessage(self, user, numeric, *params, **kw):
        server = self.ircd.servers[user.uuid[:3]]
        server.sendMessage("PUSH", user.uuid, "::{} {} {}".format(kw["prefix"], numeric, " ".join(params)), prefix=self.ircd.serverID)
        return True

class UserAdmin(Command):
    implements(ICommand)
    
    def __init__(self, ircd, sendFunc):
        self.ircd = ircd
        self.sendFunc = sendFunc
    
    def parseParams(self, user, params, prefix, tags):
        if not params:
            return {}
        if params[0] == self.ircd.name:
            return {}
        if params[0] not in self.ircd.serverNames:
            user.sendSingleError("AdminServer", irc.ERR_NOSUCHSERVER, params[0], ":No such server")
            return None
        return {
            "server": self.ircd.servers[self.ircd.serverNames[params[0]]]
        }
    
    def execute(self, user, data):
        if "server" in data:
            server = data["server"]
            server.sendMessage("ADMINREQ", server.serverID, prefix=user.uuid)
        else:
            self.sendFunc(user, self.ircd.name)
        return True

class ServerAdmin(Command):
    implements(ICommand)
    
    def __init__(self, ircd, sendFunc):
        self.ircd = ircd
        self.sendFunc = sendFunc
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 1:
            return None
        if prefix not in self.ircd.users:
            return None
        if params[0] == self.ircd.serverID:
            return {
                "fromuser": self.ircd.users[prefix]
            }
        if params[0] not in self.ircd.servers:
            return None
        return {
            "fromuser": self.ircd.users[prefix],
            "server": self.ircd.servers[params[0]]
        }
    
    def execute(self, server, data):
        if "server" in data:
            server = data["server"]
            server.sendMessage("ADMINREQ", server.serverID, prefix=data["fromuser"].uuid)
        else:
            self.sendFunc(data["fromuser"], self.ircd.name)
        return True

adminCmd = AdminCommand()