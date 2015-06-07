from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class BlockCTCP(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "BlockCTCP"
	affectedActions = {
		"commandmodify-PRIVMSG": 10,
		"commandmodify-NOTICE": 10
	}
	
	def channelModes(self):
		return [ ("C", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-C-commandmodify-PRIVMSG", 10, self.channelHasMode),
		         ("modeactioncheck-channel-C-commandmodify-NOTICE", 10, self.channelHasMode) ]
	
	def channelHasMode(self, channel, user, data):
		if "C" in channel.modes:
			return ""
		return None
	
	def apply(self, actionName, channel, param, user, data):
		if "targetchans" not in data:
			return
		if channel not in data["targetchans"]:
			return
		message = data["targetchans"][channel]
		if "\x01" not in message:
			return
		inCTCP = False
		for index, char in enumerate(message):
			if char == "\x01":
				if inCTCP:
					inCTCP = False
				else:
					if message[index+1:index+8] != "ACTION ":
						del data["targetchans"][channel]
						user.sendMessage(irc.ERR_CANNOTSENDTOCHAN, channel.name, "Can't send CTCP to channel")
						return
					inCTCP = True

blockCTCP = BlockCTCP()