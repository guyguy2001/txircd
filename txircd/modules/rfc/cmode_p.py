from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class PrivateMode(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "PrivateMode"
	core = True
	affectedActions = { "displaychannel": 10 }
	
	def channelModes(self):
		return [ ("p", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-p-displaychannel", 1, self.chanIsPrivate) ]
	
	def chanIsPrivate(self, channel, displayData, sameChannel, user, usedSearchMask):
		if "p" in channel.modes:
			return True
		return None
	
	def apply(self, actionName, channel, param, displayData, sameChannel, user, usedSearchMask):
		if usedSearchMask:
			displayData.clear()
		elif user not in channel.users:
			displayData["name"] = "*"
			displayData["modestopic"] = "[]"

privateMode = PrivateMode()