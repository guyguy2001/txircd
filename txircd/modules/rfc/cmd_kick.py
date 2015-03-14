from twisted.plugin import IPlugin
from twisted.python import log
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements
import logging

class KickCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "KickCommand"
	core = True
	
	def actions(self):
		return [ ("commandpermission-KICK", 10, self.checkKickLevel),
		         ("leavemessage", 101, self.broadcastKick),
		         ("leavemessage", 1, self.sendKickMessage) ]
	
	def userCommands(self):
		return [ ("KICK", 1, UserKick(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("KICK", 1, ServerKick(self.ircd)) ]
	
	def checkKickLevel(self, user, data):
		channel = data["channel"]
		if user not in channel.users:
			user.sendMessage(irc.ERR_NOTONCHANNEL, channel.name, "You're not on that channel")
			return False
		if not self.ircd.runActionUntilValue("checkchannellevel", "kick", channel, user):
			user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, "You don't have permission to kick users from {}".format(channel.name))
			return False
		if channel.userRank(user) < channel.userRank(data["user"]):
			user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, "You don't have permission to kick this user")
			return False
		return None
	
	def broadcastKick(self, sendUserList, channel, user, type, typeData, fromServer):
		if type != "KICK":
			return
		byUser = True
		if "byuser" in typeData:
			byUser = typeData["byuser"]
		
		sourceUser = None
		sourceServer = None
		if byUser:
			if "user" not in typeData:
				return
			sourceUser = typeData["user"]
			prefix = sourceUser.uuid
		else:
			if "server" not in typeData:
				return
			sourceServer = typeData["server"]
			prefix = sourceServer.serverID
		
		reason = sourceUser.nick if byUser else sourceServer.name
		if "reason" in typeData:
			reason = typeData["reason"]
		self.ircd.broadcastToServers(fromServer, "KICK", channel.name, user.uuid, reason, prefix=prefix)
	
	def sendKickMessage(self, sendUserList, channel, user, type, typeData, fromServer):
		if type != "KICK":
			return
		byUser = True
		if "byuser" in typeData:
			byUser = typeData["byuser"]
		
		sourceUser = None
		sourceServer = None
		kwArgs = { "to": channel.name }
		if byUser:
			if "user" not in typeData:
				return
			sourceUser = typeData["user"]
			kwArgs["sourceuser"] = sourceUser
		else:
			if "server" not in typeData:
				return
			sourceServer = typeData["server"]
			kwArgs["sourceserver"] = sourceServer
		
		reason = sourceUser.nick if byUser else sourceServer.name
		if "reason" in typeData:
			reason = typeData["reason"]
		for user in sendUserList:
			user.sendMessage("KICK", user.nick, reason, **kwArgs)
		del sendUserList[:]


class UserKick(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("KickCmd", irc.ERR_NEEDMOREPARAMS, "KICK", "Not enough parameters")
			return None
		if params[0] not in self.ircd.channels:
			user.sendSingleError("KickCmd", irc.ERR_NOSUCHCHANNEL, params[0], "No such channel")
			return None
		if params[1] not in self.ircd.userNicks:
			user.sendSingleError("KickCmd", irc.ERR_NOSUCHNICK, params[1], "No such nick")
			return None
		channel = self.ircd.channels[params[0]]
		targetUser = self.ircd.users[self.ircd.userNicks[params[1]]]
		if targetUser not in channel.users:
			user.sendSingleError("KickCmd", irc.ERR_USERNOTINCHANNEL, targetUser.nick, channel.name, "They are not on that channel")
			return None
		reason = user.nick
		if len(params) > 2:
			reason = params[2]
		return {
			"channel": channel,
			"user": targetUser,
			"reason": reason
		}
	
	def affectedUsers(self, user, data):
		return [data["user"]]
	
	def affectedChannels(self, user, data):
		return [data["channel"]]
	
	def execute(self, user, data):
		channel = data["channel"]
		targetUser = data["user"]
		reason = data["reason"]
		targetUser.leaveChannel(channel, "KICK", { "byuser": True, "user": user, "reason": reason })
		return True


class ServerKick(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 3:
			return None
		sourceType = None
		if prefix in self.ircd.users:
			sourceType = "user"
		elif prefix in self.ircd.servers:
			sourceType = "server"
		else:
			return None
		if params[0] not in self.ircd.channels:
			return None
		if params[1] not in self.ircd.users:
			return None
		return {
			"source{}".format(sourceType): self.ircd.users[prefix] if sourceType == "user" else self.ircd.servers[prefix],
			"channel": self.ircd.channels[params[0]],
			"targetuser": self.ircd.users[params[1]],
			"reason": params[2]
		}
	
	def execute(self, server, data):
		channel = data["channel"]
		sourceUser = data["sourceuser"] if "sourceuser" in data else None
		sourceServer = data["sourceserver"] if "sourceserver" in data else None
		targetUser = data["targetuser"]
		reason = data["reason"]
		
		leaveTypeData = { "reason": reason }
		if sourceUser:
			leaveTypeData["byuser"] = True
			leaveTypeData["user"] = sourceUser
		else:
			leaveTypeData["byuser"] = False
			leaveTypeData["server"] = sourceServer
		
		targetUser.leaveChannel(channel, "KICK", leaveTypeData, server)
		return True

kickCmd = KickCommand()