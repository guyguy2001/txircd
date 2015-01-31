from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, stripFormatting
from zope.interface import implements

class StripColors(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)

	name = "StripColors"
	affectedActions = [ "commandmodify-PRIVMSG", "commandmodify-NOTICE" ]

	def hookIRCd(self, ircd):
		self.ircd = ircd

	def channelModes(self):
		return [ ("S", ModeType.NoParam, self) ]

	def actions(self):
		return [ ("modeactioncheck-channel-S-commandmodify-PRIVMSG", 10, self.channelHasMode),
				("modeactioncheck-channel-S-commandmodify-NOTICE", 10, self.channelHasMode) ]

	def channelHasMode(self, channel, user, command, data):
		if "S" in channel.modes:
			return ""
		return None

	def apply(self, actionName, channel, param, user, command, data):
		minAllowedRank = self.ircd.config.getWithDefault("exempt_chanops_stripcolor", 20)
		if channel.userRank(user) < minAllowedRank and channel in data["targetchans"]:
			message = data["targetchans"][channel]
			data["targetchans"][channel] = stripFormatting(message)

	def fullUnload(self):
		for channel in self.ircd.channels.itervalues():
			if "S" in channel.modes:
				channel.setModes(self.ircd.serverID, "-S", [])

stripColors = StripColors()