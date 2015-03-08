from twisted.plugin import IPlugin
from twisted.python import log
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ircLower, ModeType
from zope.interface import implements
from fnmatch import fnmatch
import logging

class Oper(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "Oper"
	core = True
	
	def userCommands(self):
		return [ ("OPER", 1, UserOper(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("OPER", 1, ServerOper(self.ircd)) ]
	
	def actions(self):
		return [ ("userhasoperpermission", 1, self.operPermission),
		("modepermission-user-o", 1, self.nope),
		("burst", 90, self.propagatePermissions) ]
	
	def userModes(self):
		return [ ("o", ModeType.NoParam, self) ]
	
	def operPermission(self, user, permissionType):
		if "o" not in user.modes:
			# Maybe the user de-opered or something, but if they did they're clearly not an oper now
			return False
		# If the client code is just generally querying whether the user has any oper permissions, just tell it yes if the user has +o
		if not permissionType:
			return True
		# Check for oper permissions in the user's permission storage
		if "oper-permissions" not in user.cache:
			return False
		return permissionType in user.cache["oper-permissions"]
	
	def nope(self, user, settingUser, adding, param):
		if adding:
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - User mode o may not be set")
			return False
		return None
	
	def propagatePermissions(self, server):
		for user in self.ircd.users.itervalues():
			if "o" in user.modes and "oper-permissions" in user.cache:
				permString = " ".join(user.cache["oper-permissions"])
				server.sendMessage("OPER", user.uuid, permString, prefix=self.ircd.serverID)

class UserOper(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("OperCmd", irc.ERR_NEEDMOREPARAMS, "OPER", "Not enough parameters")
			return None
		return {
			"username": params[0],
			"password": params[1]
		}
	
	def execute(self, user, data):
		configuredOpers = self.ircd.config.get("opers", {})
		username = data["username"]
		if username not in configuredOpers:
			user.sendMessage(irc.ERR_NOOPERHOST, "Invalid oper credentials")
			self.reportOper(user, "Bad username")
			return True
		operData = configuredOpers[username]
		if "password" not in operData:
			user.sendMessage(irc.ERR_NOOPERHOST, "Invalid oper credentials")
			self.reportOper(user, "Bad password")
			return True
		password = data["password"]
		if "hash" in operData:
			compareFunc = "compare-{}".format(operData["hash"])
			if compareFunc not in self.ircd.functionCache:
				user.sendMessage(irc.ERR_NOOPERHOST, "Invalid oper credentials")
				self.reportOper(user, "Bad password")
				return True
			passwordMatch = self.ircd.functionCache[compareFunc](password, operData["password"])
		else:
			passwordMatch = (password == operData["password"])
		if not passwordMatch:
			user.sendMessage(irc.ERR_NOOPERHOST, "Invalid oper credentials")
			self.reportOper(user, "Bad password")
			return True
		if "host" in operData:
			operHost = ircLower(operData["host"])
			userHost = ircLower("{}@{}".format(user.ident, user.host))
			if not fnmatch(userHost, operHost):
				userHost = ircLower("{}@{}".format(user.ident, user.realHost))
				if not fnmatch(userHost, operHost):
					userHost = ircLower("{}@{}".format(user.ident, user.ip))
					if not fnmatch(userHost, operHost):
						user.sendMessage(irc.ERR_NOOPERHOST, "Invalid oper credentials")
						self.reportOper(user, "Bad host")
						return True
		if self.ircd.runActionUntilFalse("opercheck", user, username, password, operData): # Allow other modules to implement additional checks
			user.sendMessage(irc.ERR_NOOPERHOST, "Invalid oper credentials")
			self.reportOper(user, "Failed additional oper checks") #TODO: Provide a standardized way for these custom checks to give a reason
			return True
		user.setModes([(True, "o", None)], self.ircd.serverID)
		user.sendMessage(irc.RPL_YOUREOPER, "You are now an IRC operator")
		self.reportOper(user, None)
		if "types" in operData:
			configuredOperTypes = self.ircd.config.get("oper_types", {})
			operPermissions = set()
			for operType in operData["types"]:
				if operType not in configuredOperTypes:
					continue
				operPermissions.update(configuredOperTypes[operType])
			user.cache["oper-permissions"] = operPermissions
			self.ircd.broadcastToServers(None, "OPER", user.uuid, *operPermissions, prefix=self.ircd.serverID)
		return True

	def reportOper(self, user, reason):
		if reason:
			log.msg("Failed OPER attempt from {} ({})".format(user.nick, reason), logLevel=logging.WARNING)
		self.ircd.runActionStandard("operreport", user, reason)

class ServerOper(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if not params:
			return None
		if params[0] not in self.ircd.users:
			return None
		return {
			"user": self.ircd.users[params[0]],
			"permissions": params[1:]
		}
	
	def execute(self, server, data):
		user = data["user"]
		permissions = set(data["permissions"])
		user.cache["oper-permissions"] = permissions
		self.ircd.broadcastToServers(server, "OPER", user.uuid, *permissions, prefix=user.uuid[:3])
		return True

oper = Oper()