from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, ircLower, now
from zope.interface import implements
from fnmatch import fnmatchcase

class QLine(ModuleData, XLineBase):
	implements(IPlugin, IModuleData)
	
	name = "QLine"
	core = True
	lineType = "Q"
	
	def actions(self):
		return [ ("register", 10, self.checkLines),
		         ("commandpermission-NICK", 10, self.checkNick),
		         ("commandpermission-QLINE", 10, self.restrictToOper),
		         ("statsruntype-qlines", 10, self.generateInfo),
		         ("xlinetypeallowsexempt", 10, self.qlineNotExempt),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self):
		return [ ("QLINE", 1, UserQLine(self)) ]
	
	def serverCommands(self):
		return [ ("ADDLINE", 1, ServerAddQLine(self)),
		         ("DELLINE", 1, ServerDelQLine(self)) ]
	
	def load(self):
		self.initializeLineStorage()

	def verifyConfig(self, config):
		if "client_ban_msg" in config and not isinstance(config["client_ban_msg"], basestring):
			raise ConfigValidationError("client_ban_msg", "value must be a string")
	
	def checkUserMatch(self, user, mask, data):
		if data and "newnick" in data:
			return fnmatchcase(ircLower(data["newnick"]), ircLower(mask))
		return fnmatchcase(ircLower(user.nick), ircLower(mask))
	
	def changeNick(self, user, reason, hasBeenConnected):
		self.ircd.log.info("Matched user {user.uuid} ({user.nick}) against a q:line: {reason}", user=user, reason=reason)
		if hasBeenConnected:
			user.sendMessage("NOTICE", "Your nickname has been changed, as it is now invalid. ({})".format(reason))
		else:
			user.sendMessage("NOTICE", "The nickname you chose was invalid. ({})".format(reason))
		user.changeNick(user.uuid)
	
	def checkLines(self, user):
		reason = self.matchUser(user)
		if reason is not None:
			self.changeNick(user, reason, False)
		return True
	
	def checkNick(self, user, data):
		self.expireLines()
		newNick = data["nick"]
		reason = self.matchUser(user, { "newnick": newNick })
		if reason is not None:
			user.sendMessage("NOTICE", "The nickname you chose was invalid. ({})".format(reason))
			return False
		return True
	
	def restrictToOper(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-qline"):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def qlineNotExempt(self, lineType):
		if lineType == "Q":
			return False
		return True

class UserQLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("QLineParams", irc.ERR_NEEDMOREPARAMS, "QLINE", "Not enough parameters")
			return None
		if len(params) == 1:
			return {
				"mask": params[0]
			}
		return {
			"mask": params[0],
			"duration": durationToSeconds(params[1]),
			"reason": " ".join(params[2:])
		}
	
	def execute(self, user, data):
		banmask = data["mask"]
		if "reason" in data:
			if not self.module.addLine(banmask, now(), data["duration"], user.hostmask(), data["reason"]):
				user.sendMessage("NOTICE", "*** Q:Line for {} is already set.".format(banmask))
				return True
			for checkUser in self.module.ircd.users.itervalues():
				reason = self.module.matchUser(checkUser)
				if reason is not None:
					self.module.changeNick(checkUser, reason, True)
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed q:line for {} has been set, to expire in {} seconds.".format(banmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent q:line for {} has been set.".format(banmask))
			return True
		if not self.module.delLine(banmask):
			user.sendMessage("NOTICE", "*** Q:Line for {} doesn't exist.".format(banmask))
			return True
		user.sendMessage("NOTICE", "*** Q:Line for {} has been removed.".format(banmask))
		return True

class ServerAddQLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerAddParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		if self.module.executeServerAddCommand(server, data):
			for user in self.module.ircd.users.itervalues():
				reason = self.module.matchUser(user)
				if reason is not None:
					self.module.changeNick(user, reason, True)
			return True
		return None

class ServerDelQLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerDelCommand(server, data)

qlineModule = QLine()