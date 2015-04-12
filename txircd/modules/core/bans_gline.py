from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, now
from zope.interface import Implements

class GLine(ModuleData, XLineBase):
	implements(IPlugin, IModuleData)
	
	name = "GLine"
	core = True
	lineType = "G"
	
	def actions(self):
		return [ ("register", 10, self.checkLines),
		         ("commandpermission-GLINE", 10, self.restrictToOper) ]
	
	def userCommands(self):
		return [ ("GLINE", 1, UserGLine(self)) ]
	
	def serverCommands(self):
		return [ ("ADDLINE", 1, ServerGLine(self)) ]

class UserGLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("GLineParams", irc.ERR_NEEDMOREPARAMS, "GLINE", "Not enough parameters")
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
			"duration": durationToSeconds(params[1]),
			"reason": " ".join(params[2:])
		}
	
	def execute(self, user, data):
		banmask = data["mask"]
		if "reason" in data:
			if not self.addLine(banmask, now(), data["duration"], user.hostmask(), data["reason"]):
				user.sendMessage("NOTICE", "*** G:Line for {} is already set.".format(banmask))
			return True
		if not self.delLine(banmask):
			user.sendMessage("NOTICE", "*** G:Line for {} doesn't exist.".format(banmask))
		return True

class ServerGLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerCommands(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerCommand(server, data)

glineModule = GLine()