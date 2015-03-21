from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, durationToSeconds, ircLower, now, timestamp
from zope.interface import implements
from fnmatch import fnmatchcase

class ELineCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "ELineCommand"
	core = True
	exceptlist = None

	def userCommands(self):
		return [ ("ELINE", 1, self) ]

	def actions(self):
		return [ ("commandpermission-ELINE", 1, self.restrictToOpers),
				("register", 50, self.registerCheck),
				("statstypename", 1, self.checkStatsType),
				("statsruntype", 1, self.listStats),
				("addxline", 1, self.addELine),
				("removexline", 1, self.removeELine),
				("burst", 10, self.burstELines) ]

	def restrictToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-eline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("ElineParams", irc.ERR_NEEDMOREPARAMS, "ELINE", "Not enough parameters")
			return None
		else:
			exceptmask = params[0]
			for u in self.ircd.users.itervalues():
				if exceptmask == u.nick:
					exceptmask = "{}@{}".format(u.ident, u.realHost)
					break
			if "@" not in exceptmask:
				exceptmask = "*@{}".format(exceptmask)
			exceptmask = ircLower(exceptmask)
			self.expireELines()
			if len(params) == 1:
				# Unsetting E:line
				return {
					"user": user,
					"mask": exceptmask
				}
			elif len(params) == 3:
				# Setting E:line
				return {
					"user": user,
					"mask": exceptmask,
					"duration": durationToSeconds(params[1]),
					"reason": " ".join(params[2:])
				}

	def execute(self, user, data):
		exceptmask = data["mask"]
		if "reason" not in data:
			# Unsetting E:line
			if exceptmask not in self.exceptlist:
				user.sendMessage("NOTICE", "*** E:Line for {} does not currently exist; check /stats E for a list of active E:Lines.".format(exceptmask))
			else:
				self.removeELine("E", exceptmask)
				self.ircd.runActionStandard("propagateremovexline", "E", exceptmask)
				user.sendMessage("NOTICE", "*** E:Line removed on {}.".format(exceptmask))
		else:
			# Setting E:line
			duration = data["duration"]
			if exceptmask in self.exceptlist:
				user.sendMessage("NOTICE", "*** There's already a E:Line set on {}! Check /stats E for a list of active E:Lines.".format(exceptmask))
			else:
				setter = user.hostmaskWithRealHost()
				createdTS = timestamp(now())
				reason = data["reason"]
				self.addELine("E", exceptmask, setter, createdTS, duration, reason)
				self.ircd.runActionStandard("propagateaddxline", "E", exceptmask, setter, createdTS, duration, reason)
				if duration > 0:
					user.sendMessage("NOTICE", "*** Timed E:Line added on {}, to expire in {} seconds.".format(exceptmask, duration))
				else:
					user.sendMessage("NOTICE", "*** Permanent E:Line added on {}.".format(exceptmask))
		return True

	def addELine(self, linetype, mask, setter, created, duration, reason):
		if linetype != "E" or mask in self.exceptlist:
			return
		self.exceptlist[mask] = {
					"setter": setter,
					"created": created,
					"duration": duration,
					"reason": reason
				}
		self.ircd.storage["elines"] = self.exceptlist
		for user in self.ircd.users.itervalues():
			if self.matchELine(user):
				user.cache["eline_match"] = True

	def removeELine(self, linetype, mask):
		if linetype != "E" or mask not in self.exceptlist:
			return
		del self.exceptlist[mask]
		self.ircd.storage["elines"] = self.exceptlist
		bannedUsers = {}
		for u in self.ircd.users.itervalues():
			# Clear E:line cache and rematch
			if "eline_match" in u.cache:
				del u.cache["eline_match"]
			if self.matchELine(u):
				u.cache["eline_match"] = True
			result = self.ircd.runActionUntilValue("xlinerematch", user)
			if result:
				bannedUsers[u] = result
		for u, reason in bannedUsers.iteritems():
			if u.uuid[:3] == self.ircd.serverID:
				u.sendMessage("NOTICE", self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@xyz.com for help."))
				u.disconnect("Banned: Exception removed ({})".format(reason))

	def burstELines(self, server):
		self.expireELines()
		self.ircd.runActionStandard("burstxlines", server, "E", self.exceptlist)

	def registerCheck(self, user):
		self.expireELines()
		result = self.matchELine(user)
		if result:
			user.cache["eline_match"] = result
		return True

	def checkStatsType(self, typeName):
		if typeName == "E":
			return "ELINES"
		return None

	def listStats(self, user, typeName):
		if typeName == "ELINES":
			self.expireELines()
			elines = {}
			for mask, linedata in self.exceptlist.iteritems():
				elines[mask] = "{} {} {} :{}".format(linedata["created"], linedata["duration"], linedata["setter"], linedata["reason"])
			return elines
		return None

	def matchELine(self, user):
		if "eline_match" in user.cache:
			return user.cache["eline_match"]
		self.expireELines()
		toMatch = ircLower("{}@{}".format(user.ident, user.realHost))
		for mask, linedata in self.exceptlist.iteritems():
			if fnmatchcase(toMatch, mask):
				user.cache["eline_match"] = linedata["reason"]
				return user.cache["eline_match"]
		toMatch = ircLower("{}@{}".format(user.ident, user.ip))
		for mask, linedata in self.exceptlist.iteritems():
			if fnmatchcase(toMatch, mask):
				user.cache["eline_match"] = linedata["reason"]
				return user.cache["eline_match"]

	def expireELines(self):
		currentTime = timestamp(now())
		expiredLines = []
		for mask, linedata in self.exceptlist.iteritems():
			if linedata["duration"] and currentTime > linedata["created"] + linedata["duration"]:
				expiredLines.append(mask)
		for mask in expiredLines:
			del self.exceptlist[mask]
		if len(expiredLines) > 1:
			# Only write to storage when we actually modify something
			self.ircd.storage["elines"] = self.exceptlist

	def load(self):
		if "elines" not in self.ircd.storage:
			self.ircd.storage["elines"] = CaseInsensitiveDictionary()
		self.exceptlist = self.ircd.storage["elines"]

eline = ELineCommand()