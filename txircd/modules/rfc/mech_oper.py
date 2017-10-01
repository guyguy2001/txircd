from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ircLower, isValidHost, ModeType
from zope.interface import implementer
from fnmatch import fnmatchcase

@implementer(IPlugin, IModuleData, IMode)
class Oper(ModuleData, Mode):
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

	def verifyConfig(self, config):
		if "oper_types" in config:
			if not isinstance(config["oper_types"], dict):
				raise ConfigValidationError("oper_types", "value must be a dictionary")
			for operType, permissions in config["oper_types"].items():
				if not isinstance(operType, str):
					raise ConfigValidationError("oper_types", "every oper type must be a string")
				if not isinstance(permissions, list):
					raise ConfigValidationError("oper_types", "permissions for oper type \"{}\" must be a list".format(operType))
				for permission in permissions:
					if not isinstance(permission, str):
						raise ConfigValidationError("oper_types", "every permission for oper type \"{}\" must be a string".format(operType))
		else:
			config["oper_types"] = {}
		
		if "oper_groups" in config:
			if not isinstance(config["oper_groups"], dict):
				raise ConfigValidationError("oper_groups", "value must be a dictionary")
			for groupName, values in config["oper_groups"].items():
				if not isinstance(groupName, str):
					raise ConfigValidationError("oper_groups", "all group names must be strings")
				if not isinstance(values, dict):
					raise ConfigValidationError("oper_groups", "group data must be a dict")
				for groupDataKey, groupDataValue in values.items():
					if not isinstance(groupDataKey, str):
						raise ConfigValidationError("oper_groups", "group data identifiers for oper group \"{}\" must all be strings".format(groupName))
					if groupDataKey == "vhost" and (not isinstance(groupDataValue, str) or not isValidHost(groupDataValue)):
						raise ConfigValidationError("oper_groups", "vhosts for oper group \"{}\" must all be valid hostnames".format(groupName))
					if groupDataKey == "types":
						if not isinstance(groupDataValue, list):
							raise ConfigValidationError("oper_groups", "oper type lists for oper group \"{}\" must all be lists".format(groupName))
						for operType in groupDataValue:
							if not isinstance(operType, str):
								raise ConfigValidationError("oper_groups", "all oper type names for oper group \"{}\" must be strings".format(groupName))
							if operType not in config["oper_types"]:
								raise ConfigValidationError("oper_groups", "the type \"{}\" for oper group \"{}\" does not exist as an oper type".format(operType, groupName))
		else:
			config["oper_groups"] = {}
		
		if "opers" in config:
			if not isinstance(config["opers"], dict):
				raise ConfigValidationError("opers", "value must be a dictionary")
			for operName, values in config["opers"].items():
				if not isinstance(values, dict):
					raise ConfigValidationError("opers", "oper data must be a dict")
				hasPassword = False
				for operDataKey, operDataValue in values.items():
					if not isinstance(operDataKey, str):
						raise ConfigValidationError("opers", "oper data identifiers must all be strings")
					if operDataKey == "password":
						if not isinstance(operDataValue, str):
							raise ConfigValidationError("opers", "no password defined for oper \"{}\"".format(operName))
						hasPassword = True
					if operDataKey == "hash" and not isinstance(operDataValue, str):
						raise ConfigValidationError("opers", "hash type for oper \"{}\" must be a string name".format(operName))
					if operDataKey == "host" and not isinstance(operDataValue, str):
						raise ConfigValidationError("opers", "hosts for oper \"{}\" must be a string".format(operName))
					if operDataKey == "vhost" and (not isinstance(operDataValue, str) or not isValidHost(operDataValue)):
						raise ConfigValidationError("opers", "vhost for oper \"{}\" must be a valid hostname".format(operName))
					if operDataKey == "types":
						if not isinstance(operDataValue, list):
							raise ConfigValidationError("opers", "type list for oper \"{}\" must be a list".format(operName))
						for operType in operDataValue:
							if not isinstance(operType, str):
								raise ConfigValidationError("opers", "every type name for oper \"{}\" must be a string".format(operName))
							if operType not in config["oper_types"]:
								raise ConfigValidationError("opers", "the type \"{}\" for oper \"{}\" does not exist as an oper type".format(operType, operName))
					if operDataKey == "group":
						if not isinstance(operDataValue, str):
							raise ConfigValidationError("opers", "the group name for oper \"{}\" must be a string".format(operName))
						if operDataValue not in config["oper_groups"]:
							raise ConfigValidationError("opers", "the group \"{}\" for oper \"{}\" does not exist as an oper group".format(operDataValue, operName))
				if not hasPassword:
					raise ConfigValidationError("opers", "oper \"{}\" doesn't have a password specified".format(operName))
	
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
		for operPerm in user.cache["oper-permissions"]:
			if fnmatchcase(permissionType, operPerm):
				return True
		return False
	
	def nope(self, user, settingUser, adding, param):
		if adding:
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - User mode o may not be set")
			return False
		return None
	
	def propagatePermissions(self, server):
		for user in self.ircd.users.values():
			if "o" in user.modes and "oper-permissions" in user.cache:
				permString = " ".join(user.cache["oper-permissions"])
				server.sendMessage("OPER", user.uuid, permString, prefix=self.ircd.serverID)

@implementer(ICommand)
class UserOper(Command):
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
			validateFunc = "validate-{}".format(operData["hash"])
			if validateFunc in self.ircd.functionCache and not self.ircd.functionCache[validateFunc](operData["password"]):
				self.ircd.log.error("The password for {username} is not a correct hash of the type configured!", username=username)
				self.reportOper(user, "Misconfigured password hash")
				return True
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
			hosts = ircLower(operData["host"]).split(" ")
			for operHost in hosts:
				userHost = ircLower("{}@{}".format(user.ident, user.host()))
				if fnmatchcase(userHost, operHost):
					break
				userHost = ircLower("{}@{}".format(user.ident, user.realHost))
				if fnmatchcase(userHost, operHost):
					break
				userHost = ircLower("{}@{}".format(user.ident, user.ip))
				if fnmatchcase(userHost, operHost):
					break
			else:
				user.sendMessage(irc.ERR_NOOPERHOST, "Invalid oper credentials")
				self.reportOper(user, "Bad host")
				return True
		if self.ircd.runActionUntilFalse("opercheck", user, username, password, operData): # Allow other modules to implement additional checks
			user.sendMessage(irc.ERR_NOOPERHOST, "Invalid oper credentials")
			if "error" in operData:
				self.reportOper(user, operData["error"])
			else:
				self.reportOper(user, "Failed additional oper checks")
			return True
		user.setModes([(True, "o", None)], self.ircd.serverID)
		user.sendMessage(irc.RPL_YOUREOPER, "You are now an IRC operator")
		self.reportOper(user, None)
		vhost = None
		if "vhost" in operData:
			vhost = operData["vhost"]
		operPermissions = set()
		configuredOperTypes = self.ircd.config["oper_types"]
		if "types" in operData:
			for operType in operData["types"]:
				operPermissions.update(configuredOperTypes[operType])
		if "group" in operData:
			groupData = self.ircd.config["oper_groups"][operData["group"]]
			if not vhost and "vhost" in groupData:
				vhost = groupData["vhost"]
			if "types" in groupData:
				for operType in groupData["types"]:
					operPermissions.update(configuredOperTypes[operType])
		user.cache["oper-permissions"] = operPermissions
		if vhost:
			user.changeHost("oper", vhost)
		self.ircd.broadcastToServers(None, "OPER", user.uuid, *operPermissions, prefix=self.ircd.serverID)
		return True

	def reportOper(self, user, reason):
		if reason:
			self.ircd.log.warn("Failed OPER attemped from user {user.uuid} ({user.nick}): {reason}", user=user, reason=reason)
			self.ircd.runActionStandard("operfail", user, reason)
			return
		self.ircd.log.info("User {user.uuid} ({user.nick}) opered up", user=user)
		self.ircd.runActionStandard("oper", user)

@implementer(ICommand)
class ServerOper(Command):
	burstQueuePriority = 85
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if not params:
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		return {
			"user": self.ircd.users[params[0]],
			"permissions": params[1:]
		}
	
	def execute(self, server, data):
		if "lostuser" in data:
			return True
		user = data["user"]
		permissions = set(data["permissions"])
		user.cache["oper-permissions"] = permissions
		self.ircd.runActionStandard("oper", user)
		self.ircd.broadcastToServers(server, "OPER", user.uuid, *permissions, prefix=user.uuid[:3])
		return True

oper = Oper()