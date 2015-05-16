from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements
from fnmatch import fnmatchcase

class RehashCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "RehashCommand"
	core = True
	
	def actions(self):
		return [ ("commandpermission-REHASH", 1, self.restrictRehashToOpers),
				("sendremoteusermessage-382", 1, self.pushRehashMessage) ]
	
	def userCommands(self):
		return [ ("REHASH", 1, UserRehash(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("REHASH", 1, ServerRehash(self.ircd)) ]
	
	def restrictRehashToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-rehash", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def pushRehashMessage(self, user, *params, **kw):
		server = self.ircd.servers[user.uuid[:3]]
		server.sendMessage("PUSH", user.uuid, ":{} {} {}".format(kw["prefix"], irc.RPL_REHASHING, " ".join(params)))
		return True

class UserRehash(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		servers = []
		serverMask = params[0]
		if fnmatchcase(self.ircd.name, serverMask):
			servers.append(None)
		for server in self.ircd.servers.itervalues():
			if fnmatchcase(server.name, serverMask):
				servers.append(server)
		if not servers:
			user.sendSingleError("RehashServer", irc.ERR_NOSUCHSERVER, params[0], "No matching servers")
			return None
		return {
			"servers": servers
		}
	
	def execute(self, user, data):
		if "servers" not in data:
			self.rehashSelf(user)
			return True
		for server in data["servers"]:
			if server is None:
				self.rehashSelf(user)
			else:
				server.sendMessage("REHASH", server.serverID, prefix=user.uuid)
		return True
	
	def rehashSelf(self, user):
		user.sendMessage(irc.RPL_REHASHING, self.ircd.config.fileName, "Rehashing")
		try:
			self.ircd.rehash()
		except ConfigError as e:
			user.sendMessage(irc.RPL_REHASHING, self.ircd.config.fileName, "Rehash failed: {}".format(e))

class ServerRehash(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if params[0] == self.ircd.name:
			return {}
		if params[0] not in self.ircd.servers:
			return None
		return {
			"source": prefix,
			"server": self.ircd.servers[params[0]]
		}
	
	def execute(self, server, data):
		if "server" in data:
			server = data["server"]
			server.sendMessage("REHASH", server.serverID, prefix=data["source"])
			return True
		source = data["source"]
		if source in self.ircd.users:
			user = self.ircd.users[source]
			user.sendMessage(irc.RPL_REHASHING, self.ircd.config.fileName, "Rehashing")
		else:
			user = None
		try:
			self.ircd.rehash()
		except ConfigError as e:
			if user:
				user.sendMessage(irc.RPL_REHASHING, self.ircd.config.fileName, "Rehash failed: {}".format(e))
		return True

rehashCmd = RehashCommand()