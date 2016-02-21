from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class BlockChannelNotices(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)

	name = "BlockChannelNotices"
	affectedActions = {
		"commandmodify-NOTICE": 10
	}

	def channelModes(self):
		return [ ("T", ModeType.NoParam, self) ]

	def actions(self):
		return [ ("modeactioncheck-channel-T-commandmodify-NOTICE", 1, self.channelHasMode) ]

	def apply(self, actionType, channel, param, user, data):
		if channel in data["targetchans"] and not self.ircd.runActionUntilValue("checkexemptchanops", "blockchannelnotice", channel, user):
			del data["targetchans"][channel]
			user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, "Cannot send NOTICE to channel (+T is set)")

	def channelHasMode(self, channel, user, data):
		if "T" in channel.modes:
			return ""
		return None

noNoticesMode = BlockChannelNotices()