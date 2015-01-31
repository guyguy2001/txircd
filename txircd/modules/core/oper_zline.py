from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, durationToSeconds, ircLower, now, timestamp
from zope.interface import implements
from fnmatch import fnmatch

class ZLineCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "ZLineCommand"
	core = True
	banlist = None

	def hookIRCd(self, ircd):
		self.ircd = ircd

	def userCommands(self):
		return [ ("ZLINE", 1, self) ]

	def actions(self):
		return [ ("commandpermission-ZLINE", 1, self.restrictToOpers),
				("userconnect", 1, self.connectCheck),
				("statstypename", 1, self.checkStatsType),
				("statsruntype", 1, self.listStats),
				("addxline", 1, self.addZLine),
				("removexline", 1, self.removeZLine),
				("burst", 10, self.burstZLines) ]

	def restrictToOpers(self, user, command, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-zline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("ZlineParams", irc.ERR_NEEDMOREPARAMS, "ZLINE", ":Not enough parameters")
			return None
		else:
			banmask = params[0]
			for u in self.ircd.users.itervalues():
				if banmask == u.nick:
					banmask = u.ip
					break
			banmask = ircLower(banmask) # TODO: Normalize IPv6?
			self.expireZLines()
			if len(params) == 1:
				# Unsetting Z:line
				return {
					"user": user,
					"mask": banmask
				}
			elif len(params) == 3:
				# Setting Z:line
				return {
					"user": user,
					"mask": banmask,
					"duration": durationToSeconds(params[1]),
					"reason": " ".join(params[2:])
				}

	def execute(self, user, data):
		banmask = data["mask"]
		if "reason" not in data:
			# Unsetting Z:line
			if banmask not in self.banlist:
				user.sendMessage("NOTICE", ":*** Z:Line for {} does not currently exist; check /stats Z for a list of active Z:Lines.".format(banmask))
			else:
				self.removeZLine("Z", banmask)
				self.ircd.runActionStandard("propagateremovexline", "Z", banmask)
				user.sendMessage("NOTICE", ":*** Z:Line removed on {}.".format(banmask))
		else:
			# Setting Z:line
			duration = data["duration"]
			if banmask in self.banlist:
				user.sendMessage("NOTICE", ":*** There's already a Z:Line set on {}! Check /stats Z for a list of active Z:Lines.".format(banmask))
			else:
				setter = user.hostmaskWithRealHost()
				createdTS = timestamp(now())
				reason = data["reason"]
				self.addZLine("Z", banmask, setter, createdTS, duration, reason)
				self.ircd.runActionStandard("propagateaddxline", "Z", banmask, setter, createdTS, duration, ":{}".format(reason))
				if duration > 0:
					user.sendMessage("NOTICE", ":*** Timed Z:Line added on {}, to expire in {} seconds.".format(banmask, duration))
				else:
					user.sendMessage("NOTICE", ":*** Permanent Z:Line added on {}.".format(banmask))
		return True

	def addZLine(self, linetype, mask, setter, created, duration, reason):
		if linetype != "Z" or mask in self.banlist:
			return
		self.banlist[mask] = {
					"setter": setter,
					"created": created,
					"duration": duration,
					"reason": reason
				}
		self.ircd.storage["zlines"] = self.banlist
		bannedUsers = {}
		for u in self.ircd.users.itervalues():
			result = self.matchZLine(u)
			if result:
				bannedUsers[u] = result
		for u, reason in bannedUsers.iteritems():
			if u.uuid[:3] == self.ircd.serverID:
				u.sendMessage("NOTICE", ":{}".format(self.ircd.config.getWithDefault("client_ban_msg", "You're banned! Email abuse@xyz.com for help.")))
				u.disconnect("Z:Lined: {}".format(reason))

	def removeZLine(self, linetype, mask):
		if linetype != "Z" or mask not in self.banlist:
			return
		del self.banlist[mask]
		del self.banlist[banmask]
		self.ircd.storage["zlines"] = self.banlist

	def burstZLines(self, server):
		self.expireZLines()
		self.ircd.runActionStandard("burstxlines", server, "Z", self.banlist)

	def connectCheck(self, user):
		self.expireZLines()
		result = self.matchZLine(user)
		if result:
			user.sendMessage("NOTICE", ":{}".format(self.ircd.config.getWithDefault("client_ban_msg", "You're banned! Email abuse@xyz.com for help.")))
			user.disconnect("Z:Lined: {}".format(result))
			return None
		return True

	def checkStatsType(self, typeName):
		if typeName == "Z":
			return "ZLINES"
		return None

	def listStats(self, user, typeName):
		if typeName == "ZLINES":
			self.expireZLines()
			zlines = {}
			for mask, linedata in self.banlist.iteritems():
				zlines[mask] = "{} {} {} :{}".format(linedata["created"], linedata["duration"], linedata["setter"], linedata["reason"])
			return zlines
		return None

	def matchZLine(self, user):
		self.expireZLines()
		for mask, linedata in self.banlist.iteritems():
			if fnmatch(user.ip, mask): # TODO: Normalize IPv6?
				return linedata["reason"]

	def expireZLines(self):
		currentTime = timestamp(now())
		expiredLines = []
		for mask, linedata in self.banlist.iteritems():
			if linedata["duration"] and currentTime > linedata["created"] + linedata["duration"]:
				expiredLines.append(mask)
		for mask in expiredLines:
			del self.banlist[mask]
		if len(expiredLines) > 1:
			# Only write to storage when we actually modify something
			self.ircd.storage["zlines"] = self.banlist

	def load(self):
		if "zlines" not in self.ircd.storage:
			self.ircd.storage["zlines"] = CaseInsensitiveDictionary()
		self.banlist = self.ircd.storage["zlines"]

zline = ZLineCommand()