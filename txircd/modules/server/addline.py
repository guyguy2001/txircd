from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class AddlineCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)

    name = "AddlineCommand"
    core = True

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def actions(self):
        return [ ("propagateaddxline", 1, self.propagateAddXLine) ]

    def serverCommands(self):
        return [ ("ADDLINE", 10, self) ]

    def propagateAddXLine(self, linetype, mask, setter, created, duration, reason):
        serverPrefix = self.ircd.serverID
        for server in self.ircd.servers:
            if server.serverID != serverPrefix: # Probably needs more spanning tree style propagation
                server.sendMessage("ADDLINE", linetype, mask, setter, created, duration, ":{}".format(reason), prefix=serverPrefix)

    def parseParams(self, server, params, prefix, tags):
        if len(params) != 6:
            return None
        linetype = params[0]
        return {
            "linetype": params[0],
            "mask": params[1],
            "setter": params[2],
            "created": params[3],
            "duration": params[4],
            "reason": params[5]
        }

    def execute(self, server, data):
        self.ircd.runActionStandard("addxline", data["linetype"], data["mask"], data["setter"], data["created"], data["duration"], data["reason"])
        return True