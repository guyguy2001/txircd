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
		         ("statsruntype-elines", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self):
		return [ ("ELINE", 1, UserELine(self)) ]
	
	def serverCommands(self):
		return [ ("ADDLINE", 1, ServerAddELine(self)),
		         ("DELLINE", 1, ServerDelELine(self)) ]
	
	def load(self):
		self.initializeLineStorage()
	
	def checkUserMatch(self, user, mask, data):
		exceptMask = ircLower(mask)
		userMask = ircLower("{}@{}".format(user.ident, user.host()))
		if fnmatchcase(userMask, exceptMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, user.realHost))
		if fnmatchcase(userMask, exceptMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, user.ip))
		if fnmatchcase(userMask, exceptMask):
			return True
		return False
	
	def checkException(self, lineType, user, mask, data):
		if lineType == "E":
			return None
		if self.matchUser(user) is not None and not self.ircd.runActionUntilFalse("xlinetypeallowsexempt", lineType):
			return False
		return None
	
	def restrictToOper(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-eline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
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
		if banmask in self.module.ircd.userNicks:
			targetUser = self.module.ircd.users[self.module.ircd.userNicks[banmask]]
			banmask = "{}@{}".format(targetUser.ident, targetUser.realHost)
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
				user.sendMessage("NOTICE", "*** E:Line for {} is already set.".format(banmask))
				return True
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
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerAddParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerAddCommand(server, data)

class ServerDelELine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerDelCommand(server, data)

elineModule = ELine()