from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, durationToSeconds, ircLower, now, timestamp
from zope.interface import implements
from fnmatch import fnmatch

class GLineCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)

    name = "GLineCommand"
    core = True

    def __init__(self):
        self.banlist = CaseInsensitiveDictionary()

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def userCommands(self):
        return [ ("GLINE", 1, self) ]

    def actions(self):
        return [ ("commandpermission-GLINE", 1, self.restrictToOpers),
                ("register", 1, self.registerCheck),
                ("statstypename", 1, self.checkStatsType),
                ("statsruntype", 1, self.listStats),
                ("xlinerematch", 1, self.matchGLine)]

    def restrictToOpers(self, user, command, data):
        if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-gline", users=[user]):
            user.sendSingleError("GlinePermission", irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
            return False
        return None

    def parseParams(self, user, params, prefix, tags):
        if len(params) < 1 or len(params) == 2:
            user.sendSingleError("GlineParams", irc.ERR_NEEDMOREPARAMS, "GLINE", ":Not enough parameters")
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
            self.expireGLines()
            if len(params) == 1:
                # Unsetting G:line
                return {
                    "user": user,
                    "mask": banmask
                }
            elif len(params) == 3:
                # Setting G:line
                return {
                    "user": user,
                    "mask": banmask,
                    "duration": durationToSeconds(params[1]),
                    "reason": " ".join(params[2:])
                }

    def execute(self, user, data):
        banmask = data["mask"]
        if "reason" not in data:
            # Unsetting G:line
            if banmask not in self.banlist:
                user.sendMessage("NOTICE", ":*** G:Line for {} does not currently exist; check /stats G for a list of active G:Lines.".format(banmask))
            else:
                del self.banlist[data["mask"]]
                self.ircd.storage["glines"] = self.banlist
                user.sendMessage("NOTICE", ":*** G:Line removed on {}".format(data["mask"]))
        else:
            # Setting G:line
            if banmask in self.banlist:
                user.sendMessage("NOTICE", ":*** There's already a G:Line set on {}! Check /stats G for a list of active G:Lines.".format(banmask))
            else:
                self.banlist[banmask] = {
                    "setter": user.hostmaskWithRealHost(),
                    "created": timestamp(now()),
                    "duration": data["duration"],
                    "reason": data["reason"]
                }
                user.sendMessage("NOTICE", ":*** G:Line added on {}, to expire in {} seconds".format(data["mask"], data["duration"]))
                self.ircd.storage["glines"] = self.banlist
                bannedUsers = {}
                for u in self.ircd.users.itervalues():
                    result = self.matchGLine(u)
                    if result:
                        bannedUsers[u.uuid] = result
                for uid, reason in bannedUsers.iteritems():
                    u = self.ircd.users[uid]
                    u.sendMessage("NOTICE", ":{}".format(self.ircd.config.getWithDefault("client_ban_msg", "You're banned! Email abuse@xyz.com for help.")))
                    u.disconnect("G:Lined: {}".format(reason))
        return True

    def registerCheck(self, user):
        self.expireGLines()
        result = self.matchGLine(user)
        if result:
            user.sendMessage("NOTICE", ":{}".format(self.ircd.config.getWithDefault("client_ban_msg", "You're banned! Email abuse@xyz.com for help.")))
            user.disconnect("G:Lined: {}".format(result))
            return None
        return True

    def checkStatsType(self, typeName):
        if typeName == "G":
            return "GLINES"
        return None

    def listStats(self, user, typeName):
        if typeName == "GLINES":
            self.expireGLines()
            glines = {}
            for mask, linedata in self.banlist.iteritems():
                glines[mask] = "{} {} {} :{}".format(linedata["created"], linedata["duration"], linedata["setter"], linedata["reason"])
            return glines
        return None

    def matchGLine(self, user):
        if "eline_match" in user.cache:
            return None
        if "gline_match" in user.cache:
            return user.cache["gline_match"]
        self.expireGLines()
        toMatch = ircLower("{}@{}".format(user.ident, user.realhost))
        for mask, linedata in self.banlist.iteritems():
            if fnmatch(toMatch, mask):
                user.cache["gline_match"] = linedata["reason"]
                return user.cache["gline_match"]
        toMatch = ircLower("{}@{}".format(user.ident, user.ip))
        for mask, linedata in self.banlist.iteritems():
            if fnmatch(toMatch, mask):
                user.cache["gline_match"] = linedata["reason"]
                return user.cache["gline_match"]

    def expireGLines(self):
        currentTime = timestamp(now())
        expiredLines = []
        for mask, linedata in self.banlist.iteritems():
            if linedata["duration"] and currentTime > linedata["created"] + linedata["duration"]:
                expiredLines.append(mask)
        for mask in expiredLines:
            del self.banlist[mask]
        if len(expiredLines) > 1:
            # Only write to storage when we actually modify something
            self.ircd.storage["glines"] = self.banlist

    def load(self):
        if "glines" not in self.ircd.storage:
            self.ircd.storage["glines"] = CaseInsensitiveDictionary()
        self.banlist = self.ircd.storage["glines"]

gline = GLineCommand()