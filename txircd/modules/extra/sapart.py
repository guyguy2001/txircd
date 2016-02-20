from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import ICommand, IModuleData, Command, ModuleData
from zope.interface import implements

class SapartCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "SapartCommand"

	def userCommands(self):
		return [ ("SAPART", 1, self) ]

	def actions(self):
		return [ ("commandpermission-SAPART", 1, self.restrictToOpers) ]

	def restrictToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-sapart", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("SapartCmd", irc.ERR_NEEDMOREPARAMS, "SAPART", "Not enough parameters")
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("SapartCmd", irc.ERR_NOSUCHNICK, params[0], "No such nick")
			return None
		if params[1] not in self.ircd.channels:
			user.sendSingleError("SapartCmd", irc.ERR_NOSUCHCHANNEL, params[1], "No such channel")
			return None
		target = self.ircd.userNicks[params[0]]
		channel = self.ircd.channels[params[1]]
		if target not in channel.users:
			user.sendSingleError("SapartCmd", irc.ERR_USERNOTINCHANNEL, params[1], "They are not on that channel")
			return None
		reason = " ".join(params[2:]) if len(params) > 2 else ""
		reason = reason[:self.ircd.config.get("part_message_length", 300)]
		return {
			"target": target,
			"channel": channel,
			"reason": reason
		}

	def affectedChannels(self, source, data):
		return [ data["channel"] ]

	def affectedUsers(self, source, data):
		return [ data["target"] ]

	def execute(self, user, data):
		target = data["target"]
		channel = data["channel"]
		reason = data["reason"]
		target.leaveChannel(channel, "PART", { "reason": reason })
		self.ircd.log.info("User {user.uuid} ({user.nick}) forcibly part user {targetUser.uuid} ({targetUser.nick}) from channel {channel.name}", user=user, targetUser=target, channel=channel)
		return True

sapart = SapartCommand()