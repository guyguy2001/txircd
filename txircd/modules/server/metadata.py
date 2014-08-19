from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class ServerMetadata(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "ServerMetadata"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("usermetadataupdate", 10, self.propagateMetadata) ]
    
    def serverCommands(self):
        return [ ("METADATA", 1, self) ]
    
    def propagateMetadata(self, user, namespace, key, oldValue, value, fromServer):
        serverPrefix = fromServer.serverID if fromServer else self.ircd.serverID
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID and server != fromServer:
                if valueParam is None:
                    server.sendMessage("METADATA", user.uuid, namespace, key, prefix=serverPrefix)
                else:
                    server.sendMessage("METADATA", user.uuid, namespace, key, ":{}".format(value), prefix=serverPrefix)
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 3 and len(params) != 4:
            return None
        if params[0] not in self.ircd.users:
            return None
        if params[1] not in ("server", "user", "client", "ext", "private"):
            return None
        data = {
            "user": self.ircd.users[params[0]],
            "namespace": params[1],
            "key": params[2]
        }
        if len(params) == 4:
            data["value"] = params[3]
        return data
    
    def execute(self, server, data):
        if "value" in data:
            value = data["value"]
        else:
            value = None
        data["user"].setMetadata(data["namespace"], data["key"], value, server)
        return True

serverMetadata = ServerMetadata()