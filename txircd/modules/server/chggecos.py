from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class ServerChgGecos(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "ServerChangeGecos"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("changegecos", 10, self.propagateGecosChange),
                ("remotechangegecos", 10, self.propagateGecosChange) ]
    
    def serverCommands(self):
        return [ ("CHGGECOS", 1, self) ]
    
    def propagateGecosChange(self, user, oldGecos, fromServer = None):
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID and server != fromServer:
                server.sendMessage("CHGGECOS", user.uuid, ":{}".format(user.gecos), prefix=self.ircd.serverID)
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2:
            return None
        if params[0] not in self.ircd.users:
            return None
        return {
            "user": self.ircd.users[params[0]],
            "gecos": params[1]
        }
    
    def execute(self, server, data):
        data["user"].changeGecos(data["gecos"], server)
        return True

chgGecos = ServerChgGecos()