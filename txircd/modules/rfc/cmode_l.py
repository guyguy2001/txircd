from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class LimitMode(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "LimitMode"
	core = True
	affectedActions = { "joinpermission": 10 }
	
	def channelModes(self):
		return [ ("l", ModeType.Param, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-l-joinpermission", 10, self.isModeSet) ]
	
	def isModeSet(self, channel, alsoChannel, user):
		if "l" in channel.modes:
			return channel.modes["l"]
		return None
	
	def checkSet(self, channel, param):
		if param.isdigit():
			return [param]
		return None
	
	def apply(self, actionType, channel, param, alsoChannel, user):
		try: # There may be cases when the parameter we're passed is in string form still (e.g. from modules other than this one)
			param = int(param)
		except ValueError:
			return None
		if len(channel.users) >= param:
			user.sendMessage(irc.ERR_CHANNELISFULL, channel.name, "Cannot join channel (Channel is full)")
			return False
		return None

limitMode = LimitMode()