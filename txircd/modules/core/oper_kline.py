from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, durationToSeconds, ircLower, now, timestamp
from zope.interface import implements
from fnmatch import fnmatch

class KLineCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "KLineCommand"
	core = True
	banlist = None

	def userCommands(self):
		return [ ("KLINE", 1, self) ]

	def actions(self):
		return [ ("commandpermission-KLINE", 1, self.restrictToOpers),
				("register", 1, self.registerCheck),
				("statstypename", 1, self.checkStatsType),
				("statsruntype", 1, self.listStats),
				("xlinerematch", 1, self.matchKLine)]

	def restrictToOpers(self, user, command, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-kline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("KlineParams", irc.ERR_NEEDMOREPARAMS, "KLINE", "Not enough parameters")
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
			self.expireKLines()
			if len(params) == 1:
				# Unsetting K:line
				return {
					"user": user,
					"mask": banmask
				}
			elif len(params) == 3:
				# Setting K:line
				return {
					"user": user,
					"mask": banmask,
					"duration": durationToSeconds(params[1]),
					"reason": " ".join(params[2:])
				}

	def execute(self, user, data):
		banmask = data["mask"]
		if "reason" not in data:
			# Unsetting K:line
			if banmask not in self.banlist:
				user.sendMessage("NOTICE", "*** K:Line for {} does not currently exist; check /stats K for a list of active K:Lines.".format(banmask))
			else:
				del self.banlist[banmask]
				self.ircd.storage["klines"] = self.banlist
				user.sendMessage("NOTICE", "*** K:Line removed on {}.".format(banmask))
		else:
			# Setting K:line
			duration = data["duration"]
			if banmask in self.banlist:
				user.sendMessage("NOTICE", "*** There's already a K:Line set on {}! Check /stats K for a list of active K:Lines.".format(banmask))
			else:
				self.banlist[banmask] = {
					"setter": user.hostmaskWithRealHost(),
					"created": timestamp(now()),
					"duration": duration,
					"reason": data["reason"]
				}
				if duration > 0:
					user.sendMessage("NOTICE", "*** Timed K:Line added on {}, to expire in {} seconds.".format(banmask, duration))
				else:
					user.sendMessage("NOTICE", "*** Permanent K:Line added on {}.".format(banmask))
				self.ircd.storage["klines"] = self.banlist
				bannedUsers = {}
				for u in self.ircd.users.itervalues():
					result = self.matchKLine(u)
					if result:
						bannedUsers[u.uuid] = result
				for uid, reason in bannedUsers.iteritems():
					u = self.ircd.users[uid]
					u.sendMessage("NOTICE", self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@xyz.com for help."))
					u.disconnect("K:Lined: {}".format(reason))
		return True

	def registerCheck(self, user):
		self.expireKLines()
		result = self.matchKLine(user)
		if result:
			user.sendMessage("NOTICE", self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@xyz.com for help."))
			user.disconnect("K:Lined: {}".format(result))
			return None
		return True

	def checkStatsType(self, typeName):
		if typeName == "K":
			return "KLINES"
		return None

	def listStats(self, user, typeName):
		if typeName == "KLINES":
			self.expireKLines()
			klines = {}
			for mask, linedata in self.banlist.iteritems():
				klines[mask] = "{} {} {} :{}".format(linedata["created"], linedata["duration"], linedata["setter"], linedata["reason"])
			return klines
		return None

	def matchKLine(self, user):
		if user.uuid[:3] != self.ircd.serverID:
			return None
		if "eline_match" in user.cache:
			return None
		if "kline_match" in user.cache:
			return user.cache["kline_match"]
		self.expireKLines()
		toMatch = ircLower("{}@{}".format(user.ident, user.realHost))
		for mask, linedata in self.banlist.iteritems():
			if fnmatch(toMatch, mask):
				user.cache["kline_match"] = linedata["reason"]
				return user.cache["kline_match"]
		toMatch = ircLower("{}@{}".format(user.ident, user.ip))
		for mask, linedata in self.banlist.iteritems():
			if fnmatch(toMatch, mask):
				user.cache["kline_match"] = linedata["reason"]
				return user.cache["kline_match"]

	def expireKLines(self):
		currentTime = timestamp(now())
		expiredLines = []
		for mask, linedata in self.banlist.iteritems():
			if linedata["duration"] and currentTime > linedata["created"] + linedata["duration"]:
				expiredLines.append(mask)
		for mask in expiredLines:
			del self.banlist[mask]
		if len(expiredLines) > 1:
			# Only write to storage when we actually modify something
			self.ircd.storage["klines"] = self.banlist

	def load(self):
		if "klines" not in self.ircd.storage:
			self.ircd.storage["klines"] = CaseInsensitiveDictionary()
		self.banlist = self.ircd.storage["klines"]

kline = KLineCommand()