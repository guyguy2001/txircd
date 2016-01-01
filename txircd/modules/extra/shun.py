from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, ircLower, now
from zope.interface import implements
from fnmatch import fnmatchcase

class Shun(ModuleData, XLineBase):
	implements(IPlugin, IModuleData)
	
	name = "Shun"
	lineType = "SHUN"
	
	def actions(self):
		return [ ("welcome", 10, self.checkLines),
		         ("changeident", 10, self.checkIdentChange),
		         ("changehost", 10, self.checkHostChange),
		         ("commandpermission", 50, self.blockShunned),
		         ("commandpermission-SHUN", 10, self.restrictToOper),
		         ("statsruntype-shuns", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self):
		return [ ("SHUN", 1, UserShun(self)) ]
	
	def serverCommands(self):
		return [ ("ADDLINE", 1, ServerAddShun(self)),
		         ("DELLINE", 1, ServerDelShun(self)) ]
	
	def load(self):
		self.initializeLineStorage()

	def verifyConfig(self, config):
		if "shun_commands" in config:
			if not isinstance(config["shun_commands"], list):
				raise ConfigValidationError("shun_commands", "value must be a list")
			for command in config["shun_commands"]:
				if not isinstance(command, basestring):
					raise ConfigValidationError("shun_commands", "\"{}\" is not a valid command".format(command))
	
	def checkUserMatch(self, user, mask, data):
		banMask = self.normalizeMask(mask)
		userMask = ircLower("{}@{}".format(user.ident, user.host()))
		if fnmatchcase(userMask, banMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, user.realHost))
		if fnmatchcase(userMask, banMask):
			return True
		userMask = ircLower("{}@{}".format(user.ident, user.ip))
		if fnmatchcase(userMask, banMask):
			return True
		return False
	
	def checkLines(self, user):
		if self.matchUser(user) is not None:
			user.cache["shunned"] = True
			self.ircd.log.info("Matched user {user.uuid} ({user.ident}@{user.host()}) against a shun", user=user)
		elif "shunned" in user.cache:
			del user.cache["shunned"]
	
	def checkIdentChange(self, user, oldIdent, fromServer):
		self.checkLines(user)
	
	def checkHostChange(self, user, hostType, oldHost, fromServer):
		if user.uuid[:3] == self.ircd.serverID:
			self.checkLines(user)
	
	def blockShunned(self, user, command, data):
		if "shunned" not in user.cache:
			return None
		if command not in self.ircd.config.get("shun_commands", ["JOIN", "PART", "QUIT", "PING", "PONG"]):
			return False
		return None
	
	def restrictToOper(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-shun", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def onShunUpdate(self):
		for user in self.ircd.users.itervalues():
			self.checkLines(user)

class UserShun(Command):
	implements(ICommand)

	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("ShunParams", irc.ERR_NEEDMOREPARAMS, "SHUN", "Not enough parameters")
			return None
		
		shunmask = params[0]
		if shunmask in self.module.ircd.userNicks:
			targetUser = self.module.ircd.users[self.module.ircd.userNicks[shunmask]]
			shunmask = "{}@{}".format(targetUser.ident, targetUser.host())
		else:
			if "@" not in shunmask:
				shunmask = "*@{}".format(shunmask)
		if len(params) == 1:
			return {
				"mask": shunmask
			}
		return {
			"mask": shunmask,
			"duration": durationToSeconds(params[1]),
			"reason": " ".join(params[2:])
		}
	
	def execute(self, user, data):
		shunmask = data["mask"]
		if "reason" in data:
			if not self.module.addLine(shunmask, now(), data["duration"], user.hostmask(), data["reason"]):
				user.sendMessage("NOTICE", "*** Shun for {} is already set.".format(shunmask))
				return True
			self.module.onShunUpdate()
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed shun for {} has been set, to expire in {} seconds.".format(shunmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent shun for {} has been set.".format(shunmask))
			return True
		if not self.module.delLine(shunmask):
			user.sendMessage("NOTICE", "*** Shun for {} doesn't exist.".format(shunmask))
			return True
		user.sendMessage("NOTICE", "*** Shun for {} has been removed.".format(shunmask))
		return True

class ServerAddShun(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerAddParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		commandSuccess = self.module.executeServerAddCommand(server, data)
		self.module.onShunUpdate()
		return commandSuccess

class ServerDelShun(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		commandSuccess = self.module.executeServerDelCommand(server, data)
		self.module.onShunUpdate()
		return commandSuccess

shunModule = Shun()