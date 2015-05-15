from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import ICommand, IModuleData, Command, ModuleData
from txircd.utils import isValidNick
from zope.interface import implements

class SanickCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "SanickCommand"

	def userCommands(self):
		return [ ("SANICK", 1, self) ]

	def actions(self):
		return [ ("commandpermission-SANICK", 1, self.restrictToOpers) ]

	def restrictToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-sanick", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("SanickCmd", irc.ERR_NEEDMOREPARAMS, "SANICK", "Not enough parameters")
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("SanickCmd", irc.ERR_NOSUCHSERVER, "No such nick/channel")
			return None
		if not isValidNick(params[1]) or len(params[1]) > self.ircd.config.get("nick_length", 32):
			user.sendSingleError("SanickCmd", irc.ERR_ERRONEUSNICKNAME, params[1], "Erroneous nickname")
			return None
		if params[1] in self.ircd.userNicks:
			otherUserID = self.ircd.userNicks[params[1]]
			if user.uuid != otherUserID:
				user.sendSingleError("SanickCmd", irc.ERR_NICKNAMEINUSE, params[1], "Nickname is already in use")
				return None
		return {
			"target": self.ircd.users[self.ircd.userNicks[params[0]]],
			"nick": params[1]
		}

	def execute(self, user, data):
		targetUser = data["target"]
		newNick = data["nick"]
		self.ircd.log.info("User {user.uuid} ({user.nick}) forcibly changed user {targetUser.uuid}'s nick from {targetUser.nick} to {newNick}", user=user, targetUser=targetUser, newNick=newNick)
		data["target"].changeNick(data["nick"])
		return True

sanick = SanickCommand()