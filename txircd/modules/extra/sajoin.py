from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.channel import InvalidChannelName, IRCChannel
from txircd.module_interface import ICommand, IModuleData, Command, ModuleData
from zope.interface import implements

class SajoinCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

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
			user.sendSingleError("SajoinCmd", irc.ERR_NOSUCHNICK, params[0], "No such nick/channel")
			return None
		channame = params[1]
		if channame[0] != "#":
			channame = "#{}".format(channame)
		if channame in self.ircd.channels:
			channel = self.ircd.channels[channame]
		else:
			try:
				channel = IRCChannel(self.ircd, channame)
			except InvalidChannelName:
				user.sendSingleError("SajoinCmd", irc.ERR_BADCHANMASK, channame, "Bad channel mask")
				return None
		return {
			"user": self.ircd.users[self.ircd.userNicks[params[0]]],
			"channel": channel
		}

	def execute(self, user, data):
		data["user"].joinChannel(data["channel"], override=True)
		return True

sajoin = SajoinCommand()