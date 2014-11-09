from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class DellineCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)

    name = "DellineCommand"
    core = True

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def actions(self):
        return [ ("propagateremovexline", 1, self.propagateRemoveXLine) ]

    def serverCommands(self):
        return [ ("DELLINE", 10, self) ]

    def propagateRemoveXLine(self, linetype, mask):
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID:
                server.sendMessage("DELLINE", linetype, mask, prefix=self.ircd.serverID)

    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2:
            return None
        return {
            "linetype": params[0],
            "mask": params[1]
        }

    def execute(self, server, data):
        self.ircd.runActionStandard("removexline", data["linetype"], data["mask"])
        for remoteServer in self.ircd.servers.itervalues():
            if remoteServer.nextClosest == self.ircd.serverID and remoteServer != server:
                remoteServer.sendMessage("DELLINE", data["linetype"], data["mask"], prefix=self.ircd.serverID)
        return True

dellineCmd = DellineCommand()