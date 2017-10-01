from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer

@implementer(IPlugin, IModuleData, IMode)
class SecretMode(ModuleData, Mode):
	name = "SecretMode"
	core = True
	affectedActions = { "displaychannel": 20,
	                    "showchannel-whois": 20 }
	
	def channelModes(self):
		return [ ("s", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-s-displaychannel", 1, self.chanIsSecretList),
		         ("modeactioncheck-channel-s-showchannel-whois", 1, self.chanIsSecretWhois) ]
	
	def chanIsSecretList(self, channel, displayData, sameChannel, user, usedSearchMask):
		if "s" in channel.modes:
			return True
		return None
	
	def chanIsSecretWhois(self, channel, sameChannel, queryUser, targetUser):
		if "s" in channel.modes:
			return True
		return None
	
	def apply(self, actionName, channel, param, *params):
		if actionName == "displaychannel":
			displayData, sameChannel, user, usedSearchMask = params
			if user not in channel.users:
				displayData.clear() # Let's make it not show the channel at all
			return
		if actionName == "showchannel-whois":
			sameChannel, queryUser, targetUser = params
			if queryUser not in channel.users:
				return False
			return None

secretMode = SecretMode()