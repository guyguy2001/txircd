from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.modules.xlinebase import XLineBase
from txircd.utils import durationToSeconds, now
from zope.interface import implements
from fnmatch import fnmatchcase
import socket

class ZLine(ModuleData, XLineBase):
	implements(IPlugin, IModuleData)
	
	name = "ZLine"
	core = True
	lineType = "Z"
	
	def actions(self):
		return [ ("userconnect", 10, self.checkLines),
		         ("commandpermission-ZLINE", 10, self.restrictToOper),
		         ("statsruntype-zlines", 10, self.generateInfo),
		         ("burst", 10, self.burstLines) ]
	
	def userCommands(self):
		return [ ("ZLINE", 1, UserZLine(self)) ]
	
	def serverCommands(self):
		return [ ("ADDLINE", 1, ServerAddZLine(self)),
		         ("DELLINE", 1, ServerDelZLine(self)) ]
	
	def load(self):
		self.initializeLineStorage()

	def verifyConfig(self, config):
		if "client_ban_msg" in config and not isinstance(config["client_ban_msg"], basestring):
			raise ConfigValidationError("client_ban_msg", "value must be a string")
	
	def checkUserMatch(self, user, mask, data):
		return fnmatchcase(user.ip, mask)
	
	def normalizeMask(self, mask):
		if ":" in mask and "*" not in mask and "?" not in mask: # Normalize non-wildcard IPv6 addresses
			try:
				return socket.inet_ntop(socket.AF_INET6, socket.inet_pton(socket.AF_INET6, mask)).lower()
			except socket.error:
				return mask.lower()
		return mask.lower()
	
	def killUser(self, user, reason):
		self.ircd.log.info("Matched user {user.uuid} ({user.ip}) against a z:line: {reason}", user=user, reason=reason)
		user.sendMessage(irc.ERR_YOUREBANNEDCREEP, self.ircd.config.get("client_ban_msg", "You're banned! Email abuse@example.com for assistance."))
		user.disconnect("Z:Lined: {}".format(reason))
	
	def checkLines(self, user):
		reason = self.matchUser(user)
		if reason is not None:
			self.killUser(user, reason)
			return False
		return True
	
	def restrictToOper(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-zline", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

class UserZLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1 or len(params) == 2:
			user.sendSingleError("ZLineParams", irc.ERR_NEEDMOREPARAMS, "ZLINE", "Not enough parameters")
			return None
		banmask = params[0]
		if banmask in self.module.ircd.userNicks:
			banmask = self.module.ircd.userNicks[banmask].ip
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
			if not self.module.addLine(data["mask"], now(), data["duration"], user.hostmask(), data["reason"]):
				user.sendMessage("NOTICE", "*** Z:Line for {} is already set.".format(banmask))
				return True
			badUsers = []
			for checkUser in self.module.ircd.users.itervalues():
				reason = self.module.matchUser(checkUser)
				if reason is not None:
					badUsers.append((checkUser, reason))
			for badUser in badUsers:
				self.module.killUser(*badUser)
			if data["duration"] > 0:
				user.sendMessage("NOTICE", "*** Timed z:line for {} has been set, to expire in {} seconds.".format(banmask, data["duration"]))
			else:
				user.sendMessage("NOTICE", "*** Permanent z:line for {} has been set.".format(banmask))
			return True
		if not self.module.delLine(data["mask"]):
			user.sendMessage("NOTICE", "*** Z:Line for {} doesn't exist.".format(banmask))
			return True
		user.sendMessage("NOTICE", "*** Z:Line for {} has been removed.".format(banmask))
		return True

class ServerAddZLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerAddParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		if self.module.executeServerAddCommand(server, data):
			badUsers = []
			for user in self.module.ircd.users.itervalues():
				reason = self.module.matchUser(user)
				if reason is not None:
					badUsers.append((user, reason))
			for user in badUsers:
				self.module.killUser(*user)
			return True
		return None

class ServerDelZLine(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.handleServerDelParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.executeServerDelCommand(server, data)

zlineModule = ZLine()