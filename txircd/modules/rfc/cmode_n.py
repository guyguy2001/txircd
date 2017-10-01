from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer

@implementer(IPlugin, IModuleData, IMode)
class NoExtMsgMode(ModuleData, Mode):
	name = "NoExtMsgMode"
	core = True
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}
	
	def channelModes(self):
		return [ ("n", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-n-commandmodify-PRIVMSG", 1, self.channelHasMode),
		         ("modeactioncheck-channel-n-commandmodify-NOTICE", 1, self.channelHasMode) ]
	
	def apply(self, actionType, channel, param, user, data):
		if user not in channel.users and channel in data["targetchans"]:
			del data["targetchans"][channel]
			user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, "Cannot send to channel (no external messages)")
	
	def channelHasMode(self, channel, user, data):
		if "n" in channel.modes:
			return ""
		return None

noExtMsgMode = NoExtMsgMode()