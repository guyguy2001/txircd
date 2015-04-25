from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, ircLower, now
from zope.interface import implements
from fnmatch import fnmatchcase

class GLine(ModuleData, XLineBase):
	implements(IPlugin, IModuleData)
	
	name = "GLine"
	core = True
	lineType = "G"
	
	def actions(self):
		return [ ("register", 10, self.checkLines),
		         ("commandpermission-GLINE", 10, self.restrictToOper),
		         ("statsruntype-glines", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self):
		return [ ("GLINE", 1, UserGLine(self)) ]
	
	def serverCommands(self):
		return [ ("ADDLINE", 1, ServerAddGLine(self)),
		         ("DELLINE", 1, ServerDelGLine(self)) ]
	
	def load(self):
		self.initializeLineStorage()
	
	def checkUserMatch(self, user, mask, data):
		banMask = self.normalizeMask(mask)
		userMask = ircLower("{}@{}".format(user.ident, user.host))
		if fnmatchcase(userMask, banMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, user.realHost))
		if fnmatchcase(userMask, banMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, user.ip))
		if fnmatchcase(userMask, banMask):
			return True
		return False
	
	def killUser(self, user, reason):
		user.sendMessage(irc.ERR_YOUREBANNEDCREEP, self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@example.com for assistance."))
		user.disconnect("G:Lined: {}".format(reason))
	
	def checkLines(self, user):
		banReason = self.matchUser(user)
		if banReason:
			self.killUser(user, banReason)
			return False
		return True
	
	def restrictToOper(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-gline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

class UserGLine(Command):
	implements(ICommand)

	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("GLineParams", irc.ERR_NEEDMOREPARAMS, "GLINE", "Not enough parameters")
			return None
		
		banmask = params[0]
		if banmask in self.module.ircd.userNicks:
			targetUser = self.module.ircd.users[self.module.ircd.userNicks[banmask]]
			banmask = "{}@{}".format(targetUser.ident, targetUser.host)
		else:
			if "@" not in banmask:
				banmask = "*@{}".format(banmask)
		if len(params) == 1:
			return {
				"mask": banmask
			}
		return {
			"mask": banmask,
			"duration": durationToSeconds(params[1]),
			"reason": " ".join(params[2:])
		}
	
	def execute(self, user, data):
		banmask = data["mask"]
		if "reason" in data:
			if not self.module.addLine(banmask, now(), data["duration"], user.hostmask(), data["reason"]):
				user.sendMessage("NOTICE", "*** G:Line for {} is already set.".format(banmask))
				return True
			badUsers = []
			for checkUser in self.module.ircd.users.itervalues():
				reason = self.module.matchUser(checkUser)
				if reason:
					badUsers.append((checkUser, reason))
			for badUser in badUsers:
				self.module.killUser(*badUser)
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed g:line for {} has been set, to expire in {} seconds.".format(banmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent g:line for {} has been set.".format(banmask))
			return True
		if not self.module.delLine(banmask):
			user.sendMessage("NOTICE", "*** G:Line for {} doesn't exist.".format(banmask))
			return True
		user.sendMessage("NOTICE", "*** G:Line for {} has been removed.".format(banmask))
		return True

class ServerAddGLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerAddParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerAddCommand(server, data)

class ServerDelGLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerDelCommand(server, data)

glineModule = GLine()