from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class PartCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "PartCommand"
	core = True
	
	def actions(self):
		return [ ("leavemessage", 101, self.broadcastPart),
		        ("leavemessage", 1, self.sendPartMessage) ]
	
	def userCommands(self):
		return [ ("PART", 1, UserPart(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("PART", 1, ServerPart(self.ircd)) ]
	
	def broadcastPart(self, sendUserList, channel, user, type, typeData, fromServer):
		if type != "PART":
			return
		reason = ""
		if "reason" in typeData:
			reason = typeData["reason"]
		self.ircd.broadcastToServers(fromServer, "PART", channel.name, reason, prefix=user.uuid)
	
	def sendPartMessage(self, sendUserList, channel, user, type, typeData, fromServer):
		if type != "PART":
			return
		if "reason" in typeData:
			reason = typeData["reason"]
			for destUser in sendUserList:
				if destUser.uuid[:3] == self.ircd.serverID:
					destUser.sendMessage("PART", reason, to=channel.name, sourceuser=user)
		else:
			for destUser in sendUserList:
				if destUser.uuid[:3] == self.ircd.serverID:
					destUser.sendMessage("PART", to=channel.name, sourceuser=user)
		del sendUserList[:]

class UserPart(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params or not params[0]:
			user.sendSingleError("PartCmd", irc.ERR_NEEDMOREPARAMS, "PART", "Not enough parameters")
			return None
		if params[0] not in self.ircd.channels:
			user.sendSingleError("PartCmd", irc.ERR_NOSUCHCHANNEL, params[0], "No such channel")
			return None
		channel = self.ircd.channels[params[0]]
		if user not in channel.users:
			return None
		reason = params[1] if len(params) > 1 else ""
		reason = reason[:self.ircd.config.get("part_message_length", 300)]
		return {
			"channel": channel,
			"reason": reason
		}
	
	def affectedChannels(self, user, data):
		return [ data["channel"] ]
	
	def execute(self, user, data):
		channel = data["channel"]
		reason = data["reason"]
		sendUserList = channel.users.keys()
		user.leaveChannel(channel, "PART", { "reason": reason })
		return True

class ServerPart(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2 or not params[0]:
			return None
		if prefix not in self.ircd.users:
			return None
		if params[0] not in self.ircd.channels:
			return None
		return {
			"user": self.ircd.users[prefix],
			"channel": self.ircd.channels[params[0]],
			"reason": params[1]
		}
	
	def execute(self, server, data):
		user = data["user"]
		channel = data["channel"]
		reason = data["reason"]
		user.leaveChannel(channel, "PART", { "reason": reason }, server)
		return True

partCommand = PartCommand()