from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

irc.RPL_ADMINLOC1 = "257"
irc.RPL_ADMINLOC2 = "258"

@implementer(IPlugin, IModuleData)
class AdminCommand(ModuleData):
	name = "AdminCommand"
	core = True
	
	def userCommands(self):
		return [ ("ADMIN", 1, UserAdmin(self)) ]
	
	def serverCommands(self):
		return [ ("ADMINREQ", 1, ServerAdminRequest(self)),
		         ("ADMININFO", 1, ServerAdminResponse(self.ircd)) ]

	def verifyConfig(self, config):
		if "admin_line_1" in config and not isinstance("admin_server", basestring):
			raise ConfigValidationError("admin_server", "value must be a string")
		if "admin_line_2" in config and not isinstance("admin_admin", basestring):
			raise ConfigValidationError("admin_admin", "value must be a string")
		if "admin_contact" in config and not isinstance("admin_email", basestring):
			raise ConfigValidationError("admin_email", "value must be a string")
	
	def adminResponses(self):
		adminLoc1 = self.ircd.config.get("admin_line_1", "")
		if not adminLoc1: # If the line is blank, let's provide a default value
			adminLoc1 = "This server has no admins. Anarchy!"
		adminLoc2 = self.ircd.config.get("admin_line_2", "")
		if not adminLoc2:
			adminLoc2 = "Nobody configured the second line of this."
		adminContact = self.ircd.config.get("admin_contact", "")
		if not adminContact:
			adminContact = "No Admin <anarchy@example.com>"
		return (adminLoc1, adminLoc2, adminContact)

@implementer(ICommand)
class UserAdmin(Command):
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		if params[0] == self.ircd.name:
			return {}
		if params[0] not in self.ircd.serverNames:
			user.sendSingleError("AdminServer", irc.ERR_NOSUCHSERVER, params[0], "No such server")
			return None
		return {
			"server": self.ircd.serverNames[params[0]]
		}
	
	def execute(self, user, data):
		if "server" in data:
			server = data["server"]
			server.sendMessage("ADMINREQ", server.serverID, prefix=user.uuid)
		else:
			user.sendMessage(irc.RPL_ADMINME, self.ircd.name, "Administrative info for {}".format(self.ircd.name))
			adminLoc1, adminLoc2, adminContact = self.module.adminResponses()
			user.sendMessage(irc.RPL_ADMINLOC1, adminLoc1)
			user.sendMessage(irc.RPL_ADMINLOC2, adminLoc2)
			user.sendMessage(irc.RPL_ADMINEMAIL, adminContact)
		return True

@implementer(ICommand)
class ServerAdminRequest(Command):
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if prefix not in self.ircd.users:
			if prefix in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		if params[0] == self.ircd.serverID:
			return {
				"fromuser": self.ircd.users[prefix]
			}
		if params[0] not in self.ircd.servers:
			if params[0] in self.ircd.recentlyQuitServers:
				return {
					"lostserver": True
				}
			return None
		return {
			"fromuser": self.ircd.users[prefix],
			"server": self.ircd.servers[params[0]]
		}
	
	def execute(self, server, data):
		if "lostuser" in data or "lostserver" in data:
			return True
		if "server" in data:
			server = data["server"]
			server.sendMessage("ADMINREQ", server.serverID, prefix=data["fromuser"].uuid)
		else:
			toUser = data["fromuser"]
			toServer = self.ircd.servers[toUser.uuid[:3]]
			adminLoc1, adminLoc2, adminContact = self.module.adminResponses()
			tags = {
				"loc1": adminLoc1,
				"loc2": adminLoc2,
				"contact": adminContact
			}
			toServer.sendMessage("ADMININFO", toUser.uuid, prefix=self.ircd.serverID, tags=tags)
		return True

@implementer(ICommand)
class ServerAdminResponse(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if prefix not in self.ircd.servers:
			if prefix in self.ircd.recentlyQuitServers:
				return {
					"lostserver": True
				}
			return None
		if "loc1" not in tags or "loc2" not in tags or "contact" not in tags:
			return None
		if len(params) != 1:
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		return {
			"user": self.ircd.users[params[0]],
			"fromserver": self.ircd.servers[prefix],
			"loc1": tags["loc1"],
			"loc2": tags["loc2"],
			"contact": tags["contact"]
		}
	
	def execute(self, server, data):
		if "lostuser" in data or "lostserver" in data:
			return True
		user = data["user"]
		fromServer = data["fromserver"]
		if user.uuid[:3] == self.ircd.serverID:
			user.sendMessage(irc.RPL_ADMINLOC1, data["loc1"], prefix=fromServer.name)
			user.sendMessage(irc.RPL_ADMINLOC2, data["loc2"], prefix=fromServer.name)
			user.sendMessage(irc.RPL_ADMINEMAIL, data["contact"], prefix=fromServer.name)
			return True
		tags = {
			"loc1": data["loc1"],
			"loc2": data["loc2"],
			"contact": data["contact"]
		}
		self.ircd.servers[user.uuid[:3]].sendMessage("ADMININFO", user.uuid, prefix=fromServer.serverID, tags=tags)
		return True

adminCmd = AdminCommand()