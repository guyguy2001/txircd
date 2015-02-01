from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import ICommand, IModuleData, ModuleData, Command
from zope.interface import implements

class SakickCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "SakickCommand"

	def userCommands(self):
		return [ ("SAKICK", 1, self) ]

	def actions(self):
		return [ ("commandpermission-SAKICK", 1, self.restrictToOpers) ]

	def restrictToOpers(self, user, command, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-sakick", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def affectedChannels(self, source, data):
		return [ data["channel"] ]

	def affectedUsers(self, source, data):
		return [ data["target"] ]

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("SakickCmd", irc.ERR_NEEDMOREPARAMS, "SAKICK", "Not enough parameters")
			return None
		if params[0] not in self.ircd.channels:
			user.sendSingleError("SakickCmd", irc.ERR_NOSUCHCHANNEL, params[0], "No such channel")
			return None
		if params[1] not in self.ircd.userNicks:
			user.sendSingleError("SakickCmd", irc.ERR_NOSUCHNICK, params[1], "No such nick/channel")
			return None
		channel = self.ircd.channels[params[0]]
		target = self.ircd.users[self.ircd.userNicks[params[1]]]
		if target not in channel.users:
			user.sendSingleError("SakickCmd", irc.ERR_USERNOTINCHANNEL, params[1], "They are not on that channel")
			return None
		reason = user.nick
		if len(params) > 2:
			reason = params[2]
		return {
			"target": target,
			"channel": channel,
			"reason": reason
		}

	def execute(self, user, data):
		channel = data["channel"]
		targetUser = data["target"]
		reason = data["reason"]
		for u in channel.users.iterkeys():
			if u.uuid[:3] == self.ircd.serverID:
				u.sendMessage("KICK", targetUser.nick, reason, sourceuser=user, to=channel.name)
		for server in self.ircd.servers.itervalues():
			if server.nextClosest == self.ircd.serverID:
				server.sendMessage("KICK", channel.name, targetUser.uuid, reason, prefix=user.uuid)
		targetUser.leaveChannel(channel)
		return True

sakick = SakickCommand()