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
        return [ ("propagateremotexline", 1, self.propagateRemoveXLine) ]

    def serverCommands(self):
        return [ ("DELLINE", 10, self) ]

    def propagateRemoveXLine(self, linetype, mask):
        serverPrefix = self.ircd.serverID
        for server in self.ircd.servers:
            if server.serverID != serverPrefix: # Probably needs more spanning tree style propagation
                server.sendMessage("DELLINE", linetype, mask, prefix=serverPrefix)

    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2:
            return None
        return {
            "linetype": params[0],
            "mask": params[1]
        }

    def execute(self, server, data):
        self.ircd.runActionStandard("removexline", data["linetype"], data["mask"])
        return True