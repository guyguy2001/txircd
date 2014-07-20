from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class ServerPush(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "ServerPush"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def serverCommands(self):
        return [ ("PUSH", 1, self) ]
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2:
            return None
        if params[0] not in self.ircd.users:
            return None
        return {
            "user": self.ircd.users[params[0]],
            "line": params[1],
            "source": prefix
        }
    
    def execute(self, server, data):
        user = data["user"]
        if user.uuid[:3] == self.ircd.serverID:
            user.sendLine(data["line"])
            return True
        toServer = self.ircd.servers[user.uuid[:3]]
        toServer.sendMessage("PUSH", user.uuid, "{}".format(data["line"]), prefix=data["source"])
        return True

serverPush = ServerPush()