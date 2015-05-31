from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.RPL_ADMINLOC1 = "257"
irc.RPL_ADMINLOC2 = "258"

class AdminCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AdminCommand"
	core = True
	
	def actions(self):
		return [ ("sendremoteusermessage-256", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ADMINME, *params, **kw)),
				("sendremoteusermessage-257", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ADMINLOC1, *params, **kw)),
				("sendremoteusermessage-258", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ADMINLOC2, *params, **kw)),
				("sendremoteusermessage-259", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ADMINEMAIL, *params, **kw)) ]
	
	def userCommands(self):
		return [ ("ADMIN", 1, UserAdmin(self.ircd, self.sendAdminData)) ]
	
	def serverCommands(self):
		return [ ("ADMINREQ", 1, ServerAdmin(self.ircd, self.sendAdminData)) ]

	def verifyConfig(self, config):
		if "admin_server" in config and not isinstance("admin_server", basestring):
			raise ConfigValidationError("admin_server", "value must be a string")
		if "admin_admin" in config and not isinstance("admin_admin", basestring):
			raise ConfigValidationError("admin_admin", "value must be a string")
		if "admin_email" in config and not isinstance("admin_email", basestring):
			raise ConfigValidationError("admin_email", "value must be a string")
	
	def sendAdminData(self, user, serverName):
		user.sendMessage(irc.RPL_ADMINME, serverName, "Administrative info for {}".format(serverName))
		adminData = self.ircd.config.get("admin_server", "")
		if not adminData: # If the line is blank, let's provide a default value
			adminData = "This server has no admins. Anarchy!"
		user.sendMessage(irc.RPL_ADMINLOC1, adminData)
		adminData = self.ircd.config.get("admin_admin", "")
		if not adminData:
			adminData = "Nobody configured the second line of this."
		user.sendMessage(irc.RPL_ADMINLOC2, adminData)
		adminEmail = self.ircd.config.get("admin_email", "")
		if not adminEmail:
			adminEmail = "No Admin <anarchy@example.com>"
		user.sendMessage(irc.RPL_ADMINEMAIL, adminEmail)
	
	def pushMessage(self, user, numeric, *params, **kw):
		server = self.ircd.servers[user.uuid[:3]]
		server.sendMessage("PUSH", user.uuid, ":{} {} {}".format(kw["prefix"], numeric, " ".join(params)), prefix=self.ircd.serverID)
		return True

class UserAdmin(Command):
	implements(ICommand)
	
	def __init__(self, ircd, sendFunc):
		self.ircd = ircd
		self.sendFunc = sendFunc
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		if params[0] == self.ircd.name:
			return {}
		if params[0] not in self.ircd.serverNames:
			user.sendSingleError("AdminServer", irc.ERR_NOSUCHSERVER, params[0], "No such server")
			return None
		return {
			"server": self.ircd.servers[self.ircd.serverNames[params[0]]]
		}
	
	def execute(self, user, data):
		if "server" in data:
			server = data["server"]
			server.sendMessage("ADMINREQ", server.serverID, prefix=user.uuid)
		else:
			self.sendFunc(user, self.ircd.name)
		return True

class ServerAdmin(Command):
	implements(ICommand)
	
	def __init__(self, ircd, sendFunc):
		self.ircd = ircd
		self.sendFunc = sendFunc
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if prefix not in self.ircd.users:
			return None
		if params[0] == self.ircd.serverID:
			return {
				"fromuser": self.ircd.users[prefix]
			}
		if params[0] not in self.ircd.servers:
			return None
		return {
			"fromuser": self.ircd.users[prefix],
			"server": self.ircd.servers[params[0]]
		}
	
	def execute(self, server, data):
		if "server" in data:
			server = data["server"]
			server.sendMessage("ADMINREQ", server.serverID, prefix=data["fromuser"].uuid)
		else:
			self.sendFunc(data["fromuser"], self.ircd.name)
		return True

adminCmd = AdminCommand()