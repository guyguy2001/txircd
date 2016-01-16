from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class PrivateMode(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "PrivateMode"
	core = True
	affectedActions = { "displaychannel": 10,
	                    "showchannel-whois": 10 }
	
	def channelModes(self):
		return [ ("p", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-p-displaychannel", 1, self.chanIsPrivateList),
		         ("modeactioncheck-channel-p-showchannel-whois", 1, self.chanIsPrivateWhois) ]
	
	def chanIsPrivateList(self, channel, displayData, sameChannel, user, usedSearchMask):
		if "p" in channel.modes:
			return True
		return None
	
	def chanIsPrivateWhois(self, channel, sameChannel, queryUser, targetUser):
		if "p" in channel.modes:
			return True
		return None
	
	def apply(self, actionName, channel, param, *params):
		if actionName == "displaychannel":
			displayData, sameChannel, user, usedSearchMask = params
			if usedSearchMask:
				displayData.clear()
			elif user not in channel.users:
				displayData["name"] = "*"
				displayData["modestopic"] = "[]"
			return
		if actionName == "showchannel-whois":
			sameChannel, queryUser, targetUser = params
			if queryUser not in channel.users:
				return False
			return None

privateMode = PrivateMode()