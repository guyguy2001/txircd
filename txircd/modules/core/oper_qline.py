from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, durationToSeconds, ircLower, isValidNick, now, timestamp
from zope.interface import implements
from fnmatch import fnmatch

class QLineCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "QLineCommand"
	core = True
	banlist = None

	def userCommands(self):
		return [ ("QLINE", 1, self) ]

	def actions(self):
		return [ ("commandpermission-QLINE", 1, self.restrictToOpers),
				("commandpermission-NICK", 1, self.restrictNickChange),
				("register", 1, self.registerCheck),
				("statstypename", 1, self.checkStatsType),
				("statsruntype", 1, self.listStats),
				("addxline", 1, self.addQLine),
				("removexline", 1, self.removeQLine),
				("burst", 10, self.burstQLines) ]

	def restrictToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-qline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("GlineParams", irc.ERR_NEEDMOREPARAMS, "QLINE", "Not enough parameters")
			return None
		else:
			banmask = params[0]
			bancheck = banmask.replace("*", "")
			if not bancheck or ("*" in banmask and bancheck == "?"):
				user.sendSingleError("QlineParams", "NOTICE", "*** That Q:Line will match all nicks! Please check your nick mask and try again.")
				return None
			if not isValidNick(banmask):
				user.sendSingleError("QlineParams", "NOTICE", "*** That isn't a valid nick mask and won't match any nicks. Please check your nick mask and try again.")
				return None
			banmask = ircLower(banmask)
			self.expireQLines()
			if len(params) == 1:
				# Unsetting Q:line
				return {
					"user": user,
					"mask": banmask
				}
			elif len(params) == 3:
				# Setting Q:line
				return {
					"user": user,
					"mask": banmask,
					"duration": durationToSeconds(params[1]),
					"reason": " ".join(params[2:])
				}

	def execute(self, user, data):
		banmask = data["mask"]
		if "reason" not in data:
			# Unsetting Q:line
			if banmask not in self.banlist:
				user.sendMessage("NOTICE", "*** Q:Line for {} does not currently exist; check /stats Q for a list of active Q:Lines.".format(banmask))
			else:
				self.removeQLine("Q", banmask)
				self.ircd.runActionStandard("propagateremovexline", "Q", banmask)
				user.sendMessage("NOTICE", "*** Q:Line removed on {}.".format(banmask))
		else:
			# Setting Q:line
			duration = data["duration"]
			if banmask in self.banlist:
				user.sendMessage("NOTICE", "*** There's already a Q:Line set on {}! Check /stats Q for a list of active Q:Lines.".format(banmask))
			else:
				setter = user.hostmaskWithRealHost()
				createdTS = timestamp(now())
				reason = data["reason"]
				self.addQLine("Q", banmask, setter, createdTS, duration, reason)
				self.ircd.runActionStandard("propagateaddxline", "Q", banmask, setter, createdTS, duration, reason)
				if duration > 0:
					user.sendMessage("NOTICE", "*** Timed Q:Line added on {}, to expire in {} seconds.".format(banmask, duration))
				else:
					user.sendMessage("NOTICE", "*** Permanent Q:Line added on {}.".format(banmask))
		return True

	def addQLine(self, linetype, mask, setter, created, duration, reason):
		if linetype != "Q" or mask in self.banlist:
			return
		self.banlist[mask] = {
					"setter": setter,
					"created": created,
					"duration": duration,
					"reason": reason
				}
		self.ircd.storage["qlines"] = self.banlist
		bannedUsers = {}
		for u in self.ircd.users.itervalues():
			result = self.matchQLine(u)
			if result:
				bannedUsers[u] = result
		for u, reason in bannedUsers.iteritems():
			if u.uuid[:3] == self.ircd.serverID:
				u.changeNick(uid)
				u.sendMessage("NOTICE", "Your nickname has been changed as it is now invalid ({}).".format(reason))

	def removeQLine(self, linetype, mask):
		if linetype != "Q" or mask not in self.banlist:
			return
		del self.banlist[mask]
		self.ircd.storage["qlines"] = self.banlist

	def burstQLines(self, server):
		self.expireQLines()
		self.ircd.runActionStandard("burstxlines", server, "Q", self.banlist)

	def registerCheck(self, user):
		self.expireQLines()
		result = self.matchQLine(user)
		if result:
			user.sendMessage("NOTICE", "The nickname you chose was invalid ({}).".format(result))
			user.changeNick(user.uuid)
			return None
		return True

	def checkStatsType(self, typeName):
		if typeName == "Q":
			return "QLINES"
		return None

	def listStats(self, user, typeName):
		if typeName == "QLINES":
			self.expireQLines()
			qlines = {}
			for mask, linedata in self.banlist.iteritems():
				qlines[mask] = "{} {} {} :{}".format(linedata["created"], linedata["duration"], linedata["setter"], linedata["reason"])
			return qlines
		return None

	def restrictNickChange(self, user, command, data):
		self.expireQLines()
		if user.isRegistered():
			lowerNick = ircLower(data["nick"])
			for mask, linedata in self.banlist.iteritems():
				if fnmatch(lowerNick, mask):
					user.sendMessage(irc.ERR_ERRONEUSNICKNAME, data["nick"], "Invalid nickname: {}".format(linedata["reason"]))
					return False
		return None

	def matchQLine(self, user):
		self.expireQLines()
		lowerNick = ircLower(user.nick)
		for mask, linedata in self.banlist.iteritems():
			if fnmatch(lowerNick, mask):
				return linedata["reason"]

	def expireQLines(self):
		currentTime = timestamp(now())
		expiredLines = []
		for mask, linedata in self.banlist.iteritems():
			if linedata["duration"] and currentTime > linedata["created"] + linedata["duration"]:
				expiredLines.append(mask)
		for mask in expiredLines:
			del self.banlist[mask]
		if len(expiredLines) > 1:
			# Only write to storage when we actually modify something
			self.ircd.storage["qlines"] = self.banlist

	def load(self):
		if "qlines" not in self.ircd.storage:
			self.ircd.storage["qlines"] = CaseInsensitiveDictionary()
		self.banlist = self.ircd.storage["qlines"]

qline = QLineCommand()