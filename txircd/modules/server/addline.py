from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class AddlineCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)

    name = "ServerAddline"
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
        duration = str(duration)
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID:
                server.sendMessage("ADDLINE", linetype, mask, setter, created, duration, ":{}".format(reason), prefix=self.ircd.serverID)

    def burstXLines(self, server, linetype, lines):
        for mask, linedata in lines.iteritems():
            server.sendMessage("ADDLINE", linetype, mask, linedata["setter"], str(linedata["created"]),
                               str(linedata["duration"]), ":{}".format(linedata["reason"]), prefix=self.ircd.serverID)

    def parseParams(self, server, params, prefix, tags):
        if len(params) != 6:
            return None
        try:
            return {
                "linetype": params[0],
                "mask": params[1],
                "setter": params[2],
                "created": int(params[3]),
                "duration": int(params[4]),
                "reason": params[5]
            }
        except ValueError:
            return None

    def execute(self, server, data):
        lineType = data["linetype"]
        mask = data["mask"]
        setter = data["setter"]
        createdTS = data["created"]
        duration = data["duration"]
        reason = data["reason"]
        self.ircd.runActionStandard("addxline", lineType, mask, setter, createdTS, duration, reason)
        createdTS = str(createdTS)
        duration = str(duration)
        reason = ":{}".format(reason)
        for remoteServer in self.ircd.servers.itervalues():
            if remoteServer.nextClosest == self.ircd.serverID and remoteServer != server:
                remoteServer.sendMessage("ADDLINE", lineType, mask, setter, createdTS, duration, reason, prefix=self.ircd.serverID)
        return True

addlineCmd = AddlineCommand()