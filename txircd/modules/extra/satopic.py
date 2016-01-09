from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import ICommand, IModuleData, Command, ModuleData
from zope.interface import implements

class SatopicCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)

	name = "SatopicCommand"

	def userCommands(self):
		return [ ("SATOPIC", 1, self) ]

	def actions(self):
		return [ ("commandpermission-SATOPIC", 1, self.restrictToOpers) ]

	def restrictToOpers(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-satopic", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("SatopicCmd", irc.ERR_NEEDMOREPARAMS, "SATOPIC", "Not enough parameters")
			return None
		if params[0] not in self.ircd.channels:
			user.sendSingleError("SatopicCmd", irc.ERR_NOSUCHCHANNEL, params[0], "No such channel")
			return None
		return {
			"channel": self.ircd.channels[params[0]],
			"topic": " ".join(params[1:])[:self.ircd.config.get("topic_length", 326)]
		}

	def affectedChannels(self, user, data):
		return [ data["channel"] ]

	def execute(self, user, data):
		channel = data["channel"]
		newTopic = data["topic"]
		channel.setTopic(newTopic, user.uuid)
		self.ircd.log.info("User {user.uuid} ({user.nick}) forcibly set the topic of {channel.name} to '{newTopic}'.", user=user, channel=channel, newTopic=newTopic)
		return True

satopic = SatopicCommand()