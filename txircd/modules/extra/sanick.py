from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import ICommand, IModuleData, Command, ModuleData
from txircd.utils import isValidNick
from zope.interface import implements

class SanickCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "SanickCommand"

	def hookIRCd(self, ircd):
		self.ircd = ircd

	def userCommands(self):
		return [ ("SANICK", 1, self) ]

	def actions(self):
		return [ ("commandpermission-SANICK", 1, self.restrictToOpers) ]

	def restrictToOpers(self, user, command, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-sanick", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("SanickCmd", irc.ERR_NEEDMOREPARAMS, "SANICK", ":Not enough parameters")
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("SanickCmd", irc.ERR_NOSUCHSERVER, ":No such nick/channel")
			return None
		if not isValidNick(params[1]):
			user.sendSingleError("SanickCmd", irc.ERR_ERRONEUSNICKNAME, params[1], ":Erroneous nickname")
			return None
		if params[1] in self.ircd.userNicks:
			otherUserID = self.ircd.userNicks[params[1]]
			if user.uuid != otherUserID:
				user.sendSingleError("SanickCmd", irc.ERR_NICKNAMEINUSE, params[1], ":Nickname is already in use")
				return None
		return {
			"target": self.ircd.users[self.ircd.userNicks[params[0]]],
			"nick": params[1]
		}

	def execute(self, user, data):
		data["target"].changeNick(data["nick"])
		return True

sanick = SanickCommand()