from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class TopicLockMode(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "TopicLockMode"
	core = True
	affectedActions = { "commandpermission-TOPIC": 10 }
	chanLevel = 100
	
	def channelModes(self):
		return [ ("t", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-t-commandpermission-TOPIC", 10, self.channelHasMode) ]
	
	def load(self):
		self.rehash()
	
	def rehash(self):
		newLevel = self.ircd.config.get("channel_minimum_level_+t", 100)
		try:
			self.chanLevel = int(newLevel)
		except ValueError:
			try:
				self.chanLevel = self.ircd.channelStatuses[newLevel[0]][1]
			except KeyError:
				self.chanLevel = 100
	
	def channelHasMode(self, channel, user, command, data):
		if "t" in channel.modes:
			return ""
		return None
	
	def apply(self, actionType, channel, param, user, command, data):
		if channel.userRank(user) < self.chanLevel:
			user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, "You do not have access to change the topic on this channel")
			return False
		return None

topicLockMode = TopicLockMode()