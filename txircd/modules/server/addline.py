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
        return [ ("propagateaddxline", 1, self.propagateAddXLine),
                ("burstxlines", 10, self.burstXLines) ]

    def serverCommands(self):
        return [ ("ADDLINE", 10, self) ]

    def propagateAddXLine(self, linetype, mask, setter, created, duration, reason):
        created = str(created)
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID:
                server.sendMessage("ADDLINE", linetype, mask, setter, created, duration, ":{}".format(reason), prefix=self.ircd.serverID)

    def burstXLines(self, server, linetype, lines):
        for mask, linedata in lines.iteritems():
            server.sendMessage("ADDLINE", linetype, mask, linedata["setter"], linedata["created"],
                               linedata["duration"], ":{}".format(linedata["reason"]), prefix=self.ircd.serverID)

    def parseParams(self, server, params, prefix, tags):
        if len(params) != 6:
            return None
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
        for remoteServer in self.ircd.servers.itervalues():
            if remoteServer.nextClosest == self.ircd.serverID and remoteServer != server:
                remoteServer.sendMessage("ADDLINE", data["linetype"], data["mask"], data["setter"], data["created"], data["duration"], data["reason"], prefix=self.ircd.serverID)
        return True

addlineCmd = AddlineCommand()