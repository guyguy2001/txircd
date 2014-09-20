from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, durationToSeconds, ircLower, now, timestamp
from zope.interface import implements
from fnmatch import fnmatch

class ShunCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)

    name = "ShunCommand"

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def userCommands(self):
        return [ ("SHUN", 1, self) ]

    def actions(self):
        return [ ("commandpermission-SHUN", 1, self.restrictToOpers),
                ("commandpermission", 50, self.commandCheck),
                ("statstypename", 1, self.checkStatsType),
                ("statsruntype", 1, self.listStats) ]

    def restrictToOpers(self, user, command, data):
        if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-shun", users=[user]):
            user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
            return False
        return None

    def parseParams(self, user, params, prefix, tags):
        if len(params) < 1 or len(params) == 2:
            user.sendSingleError("ShunParams", irc.ERR_NEEDMOREPARAMS, "SHUN", ":Not enough parameters")
            return None
        else:
            banmask = params[0]
            for u in self.ircd.users.itervalues():
                if banmask == u.nick:
                    banmask = "{}@{}".format(u.ident, u.realhost)
                    break
            if "@" not in banmask:
                banmask = "*@{}".format(banmask)
            banmask = ircLower(banmask)
            self.expireShuns()
            if len(params) == 1:
                # Unsetting shun
                return {
                    "user": user,
                    "mask": banmask
                }
            elif len(params) == 3:
                # Setting shun
                return {
                    "user": user,
                    "mask": banmask,
                    "duration": durationToSeconds(params[1]),
                    "reason": " ".join(params[2:])
                }

    def execute(self, user, data):
        banmask = data["mask"]
        if "reason" not in data:
            # Unsetting shun
            if banmask not in self.banlist:
                user.sendMessage("NOTICE", ":*** Shun for {} does not currently exist; check /stats S for a list of active shuns.".format(banmask))
            else:
                del self.banlist[data["mask"]]
                self.ircd.storage["shuns"] = self.banlist
                user.sendMessage("NOTICE", ":*** Shun removed on {}".format(data["mask"]))
        else:
            # Setting shun
            if banmask in self.banlist:
                user.sendMessage("NOTICE", ":*** There's already a shun set on {}! Check /stats S for a list of active shuns.".format(banmask))
            else:
                self.banlist[banmask] = {
                    "setter": user.hostmaskWithRealHost(),
                    "created": timestamp(now()),
                    "duration": data["duration"],
                    "reason": data["reason"]
                }
                user.sendMessage("NOTICE", ":*** Shun added on {}, to expire in {} seconds".format(data["mask"], data["duration"]))
                self.ircd.storage["shuns"] = self.banlist
        return True

    def commandCheck(self, user, command, data):
        self.expireShuns()
        result = self.matchShun(user)
        if result and command not in self.ircd.config.getWithDefault("shun_whitelist", ["JOIN", "PART", "QUIT", "PING", "PONG"]):
            user.sendMessage("NOTICE", ":Command {} was not processed. You have been blocked from issuing commands ({}).".format(command, result))
            return False
        return None

    def checkStatsType(self, typeName):
        if typeName == "S":
            return "SHUNS"
        return None

    def listStats(self, user, typeName):
        if typeName == "SHUNS":
            self.expireShuns()
            shuns = {}
            for mask, linedata in self.banlist.iteritems():
                shuns[mask] = "{} {} {} :{}".format(linedata["created"], linedata["duration"], linedata["setter"], linedata["reason"])
            return shuns
        return None

    def matchShun(self, user):
        if "eline_match" in user.cache:
            return None
        self.expireShuns()
        toMatch = ircLower("{}@{}".format(user.ident, user.realhost))
        for mask, linedata in self.banlist.iteritems():
            if fnmatch(toMatch, mask):
                return linedata["reason"]
        toMatch = ircLower("{}@{}".format(user.ident, user.ip))
        for mask, linedata in self.banlist.iteritems():
            if fnmatch(toMatch, mask):
                return linedata["reason"]
        return None

    def expireShuns(self):
        currentTime = timestamp(now())
        expiredLines = []
        for mask, linedata in self.banlist.iteritems():
            if linedata["duration"] and currentTime > linedata["created"] + linedata["duration"]:
                expiredLines.append(mask)
        for mask in expiredLines:
            del self.banlist[mask]
        if len(expiredLines) > 1:
            # Only write to storage when we actually modify something
            self.ircd.storage["shuns"] = self.banlist

    def load(self):
        if "shuns" not in self.ircd.storage:
            self.ircd.storage["shuns"] = CaseInsensitiveDictionary()
        self.banlist = self.ircd.storage["shuns"]

shun = ShunCommand()