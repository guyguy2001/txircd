from twisted.plugin import IPlugin
from twisted.words.protocols import irc
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
		         ("statstypename", 10, self.checkStatsType),
		         ("statsruntype-QLINES", 10, self.listStats),
		         ("burst", 10, self.burstXLines) ]
	
	def userCommands(self):
		return [ ("QLINE", 1, UserQLine(self)) ]
	
	def serverCommands(self):
		return [ ("ADDLINE", 1, ServerAddQLine(self)),
		         ("DELLINE", 1, ServerDelQLine(self)) ]
	
	def checkUserMatch(self, user, mask, data):
		if data and "newnick" in data:
			return fnmatchcase(ircLower(data["newnick"]), ircLower(mask))
		return fnmatchcase(ircLower(user.nick), ircLower(mask))
	
	def changeNick(self, user, reason, hasBeenConnected):
		if hasBeenConnected:
			user.sendMessage("NOTICE", "Your nickname has been changed, as it is now invalid. ({})".format(reason))
		else:
			user.sendMessage("NOTICE", "The nickname you chose was invalid. ({})".format(reason))
		user.changeNick(user.uuid)
	
	def checkLines(self, user):
		reason = self.matchUser(user)
		if reason:
			self.changeNick(user, reason, False)
		return True
	
	def checkNick(self, user, data):
		newNick = data["nick"]
		reason = self.matchUser(user, { "newnick": newNick })
		if reason:
			user.sendMessage("NOTICE", "The nickname you chose was invalid. ({})".format(reason))
			return False
		return True
	
	def restrictToOper(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-qline"):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def checkStatsType(self, typeName):
		if typeName == "Q":
			return "QLINES"
		return None
	
	def listStats(self):
		return self.generateInfo()
	
	def burstXLines(self, server):
		self.burstLines(server)

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
				if reason:
					self.module.changeNick(checkUser, reason, True)
			user.sendMessage("NOTICE", "*** Q:Line for {} has been set.".format(banmask))
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
		return self.module.executeServerAddCommand(server, data)

class ServerDelQLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerDelCommand(server, data)

qlineModule = QLine()