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
	banlist = None

	def userCommands(self):
		return [ ("GLINE", 1, self) ]

	def actions(self):
		return [ ("commandpermission-GLINE", 1, self.restrictToOpers),
				("register", 1, self.registerCheck),
				("statstypename", 1, self.checkStatsType),
				("statsruntype", 1, self.listStats),
				("xlinerematch", 1, self.matchGLine),
				("addxline", 1, self.addGLine),
				("removexline", 1, self.removeGLine),
				("burst", 10, self.burstGLines) ]

	def restrictToOpers(self, user, command, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-gline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("GlineParams", irc.ERR_NEEDMOREPARAMS, "GLINE", "Not enough parameters")
			return None
		else:
			banmask = params[0]
			for u in self.ircd.users.itervalues():
				if banmask == u.nick:
					banmask = "{}@{}".format(u.ident, u.realHost)
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
				user.sendMessage("NOTICE", "*** G:Line for {} does not currently exist; check /stats G for a list of active G:Lines.".format(banmask))
			else:
				self.removeGLine("G", banmask)
				self.ircd.runActionStandard("propagateremovexline", "G", banmask)
				user.sendMessage("NOTICE", "*** G:Line removed on {}.".format(banmask))
		else:
			# Setting G:line
			duration = data["duration"]
			if banmask in self.banlist:
				user.sendMessage("NOTICE", "*** There's already a G:Line set on {}! Check /stats G for a list of active G:Lines.".format(banmask))
			else:
				setter = user.hostmaskWithRealHost()
				createdTS = timestamp(now())
				reason = data["reason"]
				self.addGLine("G", banmask, setter, createdTS, duration, reason)
				self.ircd.runActionStandard("propagateaddxline", "G", banmask, setter, createdTS, duration, reason)
				if duration > 0:
					user.sendMessage("NOTICE", "*** Timed G:Line added on {}, to expire in {} seconds.".format(banmask, duration))
				else:
					user.sendMessage("NOTICE", "*** Permanent G:Line added on {}.".format(banmask))
		return True

	def addGLine(self, linetype, mask, setter, created, duration, reason):
		if linetype != "G" or mask in self.banlist:
			return
		self.banlist[mask] = {
					"setter": setter,
					"created": created,
					"duration": duration,
					"reason": reason
				}
		self.ircd.storage["glines"] = self.banlist
		bannedUsers = {}
		for u in self.ircd.users.itervalues():
			result = self.matchGLine(u)
			if result:
				bannedUsers[u] = result
		for u, reason in bannedUsers.iteritems():
			if u.uuid[:3] == self.ircd.serverID:
				u.sendMessage("NOTICE", self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@xyz.com for help."))
				u.disconnect("G:Lined: {}".format(reason))

	def removeGLine(self, linetype, mask):
		if linetype != "G" or mask not in self.banlist:
			return
		del self.banlist[mask]
		self.ircd.storage["glines"] = self.banlist

	def burstGLines(self, server):
		self.expireGLines()
		self.ircd.runActionStandard("burstxlines", server, "G", self.banlist)

	def registerCheck(self, user):
		self.expireGLines()
		result = self.matchGLine(user)
		if result:
			user.sendMessage("NOTICE", self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@xyz.com for help."))
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
		toMatch = ircLower("{}@{}".format(user.ident, user.realHost))
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