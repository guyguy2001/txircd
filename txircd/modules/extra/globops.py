from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class GlobopsCommand(ModuleData):
	name = "Globops"
	
	def actions(self):
		return [ ("commandpermission-GLOBOPS", 1, self.restrictToOpers) ]
	
	def userCommands(self):
		return [ ("GLOBOPS", 1, UserGlobops(self)) ]
	
	def serverCommands(self):
		return [ ("GLOBOPS", 1, ServerGlobops(self)) ]
	
	def restrictToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-globops", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def sendGlobops(self, fromUser, message, fromServer):
		sendToServers = set()
		for targetUser in self.ircd.users.itervalues():
			if fromUser == targetUser:
				continue
			if not self.ircd.runActionUntilValue("userhasoperpermission", targetUser, "view-globops", users=[targetUser]):
				continue
			if targetUser.uuid[:3] == self.ircd.serverID:
				targetUser.sendMessage("NOTICE", "*** GLOBOPS from {}: {}".format(fromUser.nick, message))
			else:
				sendToServers.add(self.ircd.servers[targetUser.uuid[:3]])
		closestServers = set()
		for server in sendToServers:
			closestServer = server
			while closestServer.nextClosest != self.ircd.serverID:
				closestServer = self.ircd.servers[closestServer.nextClosest]
			closestServers.add(closestServer)
		if fromServer:
			closestServers.discard(fromServer)
		for server in closestServers:
			server.sendMessage("GLOBOPS", message, prefix=fromUser.uuid)

@implementer(ICommand)
class UserGlobops(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendSingleError("GlobopsParams", irc.ERR_NEEDMOREPARAMS, "GLOBOPS", "Not enough parameters")
			return None
		return {
			"message": " ".join(params)
		}
	
	def execute(self, user, data):
		self.module.sendGlobops(user, data["message"], None)
		return True

@implementer(ICommand)
class ServerGlobops(Command):
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if prefix not in self.ircd.users:
			return None
		if len(params) != 1:
			return None
		return {
			"user": self.ircd.users[prefix],
			"message": params[0]
		}
	
	def execute(self, server, data):
		self.module.sendGlobops(data["user"], data["message"], server)
		return True

globops = GlobopsCommand()