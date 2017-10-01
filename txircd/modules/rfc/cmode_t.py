from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer

@implementer(IPlugin, IModuleData, IMode)
class TopicLockMode(ModuleData, Mode):
	name = "TopicLockMode"
	core = True
	affectedActions = { "commandpermission-TOPIC": 10 }
	
	def channelModes(self):
		return [ ("t", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-t-commandpermission-TOPIC", 10, self.channelHasMode) ]
	
	def channelHasMode(self, channel, user, data):
		if "t" in channel.modes:
			return ""
		return None
	
	def apply(self, actionType, channel, param, user, data):
		if "topic" not in data:
			return None
		if not self.ircd.runActionUntilValue("checkchannellevel", "topic", channel, user, users=[user], channels=[channel]):
			user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, "You do not have access to change the topic on this channel")
			return False
		return None

topicLockMode = TopicLockMode()