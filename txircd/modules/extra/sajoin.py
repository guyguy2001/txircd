from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.channel import InvalidChannelNameError, IRCChannel
from txircd.module_interface import ICommand, IModuleData, Command, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData, ICommand)
class SajoinCommand(ModuleData, Command):
	name = "SajoinCommand"

	def userCommands(self):
		return [ ("SAJOIN", 1, self) ]

	def actions(self):
		return [ ("commandpermission-SAJOIN", 1, self.restrictToOpers) ]

	def restrictToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-sajoin", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("SajoinCmd", irc.ERR_NEEDMOREPARAMS, "SAJOIN", "Not enough parameters")
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("SajoinCmd", irc.ERR_NOSUCHNICK, params[0], "No such nick")
			return None
		channame = params[1]
		if channame[0] != "#":
			channame = "#{}".format(channame)
		if channame in self.ircd.channels:
			channel = self.ircd.channels[channame]
		else:
			try:
				channel = IRCChannel(self.ircd, channame)
			except InvalidChannelNameError:
				user.sendSingleError("SajoinCmd", irc.ERR_BADCHANMASK, channame, "Bad channel mask")
				return None
		return {
			"user": self.ircd.userNicks[params[0]],
			"channel": channel
		}

	def execute(self, user, data):
		targetUser = data["user"]
		channel = data["channel"]
		targetUser.joinChannel(channel, override=True)
		self.ircd.log.info("User {user.uuid} ({user.nick}) forcibly joined user {targetUser.uuid} ({targetUser.nick}) to channel {channel.name}", user=user, targetUser=targetUser, channel=channel)
		return True

sajoin = SajoinCommand()