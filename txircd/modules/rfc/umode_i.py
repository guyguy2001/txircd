from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class InvisibleMode(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "InvisibleMode"
	core = True
	affectedActions = {
		"showchanneluser": 1,
		"showuser": 1
	}
	
	def actions(self):
		return [ ("modeactioncheck-user-i-showchanneluser", 1, self.isInvisibleChan),
				("modeactioncheck-user-i-showuser", 1, self.isInvisibleUser) ]
	
	def userModes(self):
		return [ ("i", ModeType.NoParam, self) ]
	
	def isInvisibleChan(self, user, channel, fromUser, userSeeing):
		if "i" in user.modes:
			return True
		return None
	
	def isInvisibleUser(self, user, fromUser, userSeeing):
		if "i" in user.modes:
			return True
		return None
	
	def apply(self, actionName, user, param, *params):
		if actionName == "showchanneluser":
			return self.applyChannels(user, *params)
		return self.applyUsers(user, *params)
	
	def applyChannels(self, user, channel, fromUser, sameUser):
		if user != sameUser:
			return None
		if not channel or fromUser not in channel.users:
			return False
		return None
	
	def applyUsers(self, user, fromUser, sameUser):
		if user != sameUser:
			return None
		if set(fromUser.channels).intersection(user.channels): # Get the set intersection to see if there is any overlap
			return None
		return False

invisibleMode = InvisibleMode()