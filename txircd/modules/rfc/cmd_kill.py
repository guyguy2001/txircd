from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class KillCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "KillCommand"
	core = True
	
	def actions(self):
		return [ ("commandpermission-KILL", 1, self.restrictToOpers) ]
	
	def userCommands(self):
		return [ ("KILL", 1, UserKill(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("KILL", 1, ServerKill(self.ircd)) ]
	
	def restrictToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-kill", users=[user]):
			self.ircd.log.info("User {user.uuid} ({user.nick}) tried to kill another user", user=user)
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

class UserKill(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("KillParams", irc.ERR_NEEDMOREPARAMS, "KILL", "Not enough parameters")
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("KillTarget", irc.ERR_NOSUCHNICK, params[0], "No such nick")
			return None
		return {
			"user": self.ircd.userNicks[params[0]],
			"reason": " ".join(params[1:])
		}
	
	def affectedUsers(self, user, data):
		return [data["user"]]
	
	def execute(self, user, data):
		targetUser = data["user"]
		if targetUser.uuid[:3] == self.ircd.serverID:
			reason = data["reason"]
			targetUser.sendMessage("KILL", reason, prefix=user.hostmask())
			targetUser.disconnect("Killed by {}: {}".format(user.nick, reason))
			return True
		toServer = self.ircd.servers[targetUser.uuid[:3]]
		toServer.sendMessage("KILL", targetUser.uuid, data["reason"], prefix=user.uuid)
		return True

class ServerKill(Command):
	implements(ICommand)
	
	burstQueuePriority = 55
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if prefix not in self.ircd.servers and prefix not in self.ircd.users:
			return None
		if len(params) != 2:
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		return {
			"source": prefix,
			"target": self.ircd.users[params[0]],
			"reason": params[1]
		}
	
	def execute(self, server, data):
		if "lostuser" in data:
			return True
		user = data["target"]
		if user.uuid[:3] == self.ircd.serverID:
			fromID = data["source"]
			if fromID in self.ircd.servers:
				fromName = self.ircd.servers[fromID].name
			else:
				fromName = self.ircd.users[fromID].nick
			user.disconnect("Killed by {}: {}".format(fromName, data["reason"]))
			return True
		toServer = self.ircd.servers[user.uuid[:3]]
		toServer.sendMessage("KILL", user.uuid, data["reason"], prefix=data["source"])
		return True

killCmd = KillCommand()