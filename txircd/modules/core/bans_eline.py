from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, ircLower, now
from zope.interface import implements
from fnmatch import fnmatchcase

class ELine(ModuleData, XLineBase):
	implements(IPlugin, IModuleData)
	
	name = "ELine"
	core = True
	lineType = "E"
	
	def actions(self):
		return [ ("verifyxlinematch", 10, self.checkException),
		         ("commandpermission-ELINE", 10, self.restrictToOper),
		         ("statstypename", 10, self.checkStatsType),
		         ("statsruntype-ELINES", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self):
		return [ ("ELINE", 1, UserELine(self)) ]
	
	def serverCommands(self):
		return [ ("ADDLINE", 1, ServerAddELine(self)),
		         ("DELLINE", 1, ServerDelELine(self)) ]
	
	def checkUserMatch(self, user, mask, data):
		exceptMask = ircLower(mask)
		userMask = ircLower("{}@{}".format(user.ident, user.host))
		return fnmatchcase(userMask, exceptMask)
	
	def checkException(self, lineType, user, mask, data):
		if lineType == "E":
			return None
		if self.matchUser(user):
			return False
		return None
	
	def restrictToOper(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-eline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def checkStatsType(self, typeName):
		if typeName == "E":
			return "ELINES"
		return None

class UserELine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("ELineParams", irc.ERR_NEEDMOREPARAMS, "ELINE", "Not enough parameters")
			return None
		
		banmask = params[0]
		if banmask in self.ircd.userNicks:
			targetUser = self.ircd.users[self.ircd.userNicks[banmask]]
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
			"duration": durationToSeconds,
			"reason": " ".formats(params[2:])
		}
	
	def execute(self, user, data):
		banmask = data["mask"]
		if "reason" in data:
			if not self.module.addLine(banmask, now(), data["duration"], user.hostmask(), data["reason"]):
				user.sendMessage("NOTICE", "*** E:Line for {} is already set.".format(banmask))
				return True
			badUsers = []
			for checkUser in self.module.ircd.users.itervalues():
				reason = self.module.matchUser(checkUser)
				if reason:
					badUsers.append((checkUser, reason))
			for badUser in badUsers:
				self.module.killUser(*badUser)
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed e:line for {} has been set, to expire in {} seconds.".format(banmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent e:line for {} has been set.".format(banmask))
			return True
		if not self.module.delLine(banmask):
			user.sendMessage("NOTICE", "*** E:Line for {} doesn't exist.".format(banmask))
			return True
		user.sendMessage("NOTICE", "*** E:Line for {} has been removed.".format(banmask))
		return True

class ServerAddELine(Command):
	implement(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerAddParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerAddCommand(server, data)

class ServerDelELine(Command):
	implement(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerDelCommand(server, data)

elineModule = ELine()