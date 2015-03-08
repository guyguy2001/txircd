from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import ICommand, IModuleData, Command, ModuleData
from zope.interface import implements

class SamodeCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "SamodeCommand"

	def userCommands(self):
		return [ ("SAMODE", 1, self) ]

	def actions(self):
		return [ ("commandpermission-SAMODE", 1, self.restrictToOpers) ]

	def restrictToOpers(self, user, command, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-samode", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("SamodeCmd", irc.ERR_NEEDMOREPARAMS, "SAMODE", "Not enough parameters")
			return None
		if params[0] in self.ircd.channels:
			return {
				"targetchannel": self.ircd.channels[params[0]],
				"modes": params[1],
				"params": params[2:]
			}
		if params[0] in self.ircd.userNicks:
			return {
				"targetuser": self.ircd.users[self.ircd.userNicks[params[0]]],
				"modes": params[1],
				"params": params[2:]
			}
		user.sendSingleError("SamodeCmd", irc.ERR_NOSUCHNICK, "No such nick/channel")
		return None

	def affectedChannels(self, user, data):
		if "targetchannel" in data:
			return [ data["targetchannel"] ]
		return []

	def execute(self, user, data):
		if "targetchannel" in data:
			channel = data["targetchannel"]
			channel.setModesByUser(user.uuid, data["modes"], data["params"], True)
		elif "targetuser" in data:
			u = data["targetuser"]
			u.setModesByUser(user.uuid, data["modes"], data["params"], True)
		return True

samode = SamodeCommand()