from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements
from collections import defaultdict

irc.RPL_LOCALUSERS = "265"
irc.RPL_GLOBALUSERS = "266"

class LUsersCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "LUsersCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("welcome", 6, lambda user: self.execute(user, {})) ]
    
    def userCommands(self):
        return [ ("LUSERS", 1, self) ]

    def getStorage(self):
        return self.ircd.storage.get("user_count_max", {})
    
    def updateMaxCounts(self, counts):
        maxes = self.getStorage()
        for key in ("users", "local"):
            if counts[key] > maxes.get(key, 0):
                maxes[key] = counts[key]
        return maxes
    
    def countStats(self):
        counts = defaultdict(lambda: 0)
        counts["users"] = len(self.ircd.users)
        counts["servers"] = len(self.ircd.servers) + 1
        counts["channels"] = len(self.ircd.channels)

        for user in self.ircd.users.itervalues():
            if "i" in user.modes:
                counts["invisible"] += 1
            if "o" in user.modes:
                counts["opers"] += 1
            if user.uuid[:3] == self.ircd.serverID:
                counts["local"] += 1

        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID:
                counts["localservers"] += 1

        counts["visible"] = counts["users"] - counts["invisible"]
        maxes = self.updateMaxCounts(counts)
        return counts, maxes
    
    def parseParams(self, user, params, prefix, tags):
        return {}
    
    def execute(self, user, data):
        counts, maxes = self.countStats()
        user.sendMessage(irc.RPL_LUSERCLIENT, ":There are {counts[visible]} users and {counts[invisible]} invisible on {counts[servers]} servers".format(counts=counts))
        user.sendMessage(irc.RPL_LUSEROP, str(counts["opers"]), ":operator{} online".format("" if counts["opers"] == 1 else "s"))
        user.sendMessage(irc.RPL_LUSERCHANNELS, str(counts["channels"]), ":channel{} formed".format("" if counts["channels"] == 1 else "s"))
        user.sendMessage(irc.RPL_LUSERME, ":I have {counts[local]} clients and {counts[localservers]} servers".format(counts=counts))
        user.sendMessage(irc.RPL_LOCALUSERS, ":Current Local Users: {}  Max: {}".format(counts["local"], maxes["local"]))
        user.sendMessage(irc.RPL_GLOBALUSERS, ":Current Global Users: {}  Max: {}".format(counts["users"], maxes["users"]))
        return True

lusersCmd = LUsersCommand()