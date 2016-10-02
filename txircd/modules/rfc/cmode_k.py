from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class ChannelKeyMode(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "ChannelKeyMode"
	core = True
	affectedActions = { "commandmodify-JOIN": 10 }
	
	def channelModes(self):
		return [ ("k", ModeType.ParamOnUnset, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-k-commandmodify-JOIN", 1, self.channelPassword) ]
	
	def channelPassword(self, channel, user, data):
		if "k" in channel.modes:
			return channel.modes["k"]
		return None
	
	def checkSet(self, channel, param):
		if not param:
			return None
		password = param.split(" ")[0].replace(",", "")
		if not password:
			return None
		return [password]
	
	def checkUnset(self, channel, param):
		if "k" not in channel.modes:
			return None
		if param != channel.modes["k"]:
			return None
		return [param]
	
	def apply(self, actionType, channel, param, user, data):
		try:
			keyIndex = data["channels"].index(channel)
		except ValueError:
			return
		if data["keys"][keyIndex] != param:
			user.sendMessage(irc.ERR_BADCHANNELKEY, channel.name, "Cannot join channel (Incorrect channel key)")
			del data["channels"][keyIndex]
			del data["keys"][keyIndex]
	
	def showParam(self, user, channel):
		if user in channel.users:
			return channel.modes["k"]
		return "*"

channelKeyMode = ChannelKeyMode()