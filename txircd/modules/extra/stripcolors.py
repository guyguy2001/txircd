from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, stripFormatting
from zope.interface import implements

class StripColors(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)

	name = "StripColors"
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}

	def channelModes(self):
		return [ ("S", ModeType.NoParam, self) ]

	def actions(self):
		return [ ("modeactioncheck-channel-S-commandmodify-PRIVMSG", 10, self.channelHasMode),
				("modeactioncheck-channel-S-commandmodify-NOTICE", 10, self.channelHasMode) ]

	def channelHasMode(self, channel, user, data):
		if "S" in channel.modes:
			return ""
		return None

	def apply(self, actionName, channel, param, user, data):
		if channel in data["targetchans"] not self.ircd.runActionUntilValue("checkexemptchanops", "stripcolor", channel, user):
			message = data["targetchans"][channel]
			data["targetchans"][channel] = stripFormatting(message)

stripColors = StripColors()