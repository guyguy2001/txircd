from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

class ChannelOpAccess(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "ChannelOpAccess"
	affectedActions = {
		"checkchannellevel": 10,
		"checkexemptchanops": 10
	}
	
	def actions(self):
		return [ ("modeactioncheck-channel-W-checkchannellevel", 1, self.checkMode),
		         ("modeactioncheck-channel-W-checkexemptchanops", 1, self.checkMode) ]
	
	def channelModes(self):
		return [ ("W", ModeType.List, self) ]
	
	def checkMode(self, channel, checkType, paramChannel, user):
		if "W" not in channel.modes:
			return None
		for paramData in channel.modes["W"]:
			level, permType = paramData[0].split(":", 1)
			if permType == checkType:
				return paramData[0]
		return None
	
	def checkSet(self, channel, param):
		checkedParams = []
		for parameter in param.split(","):
			if ":" not in parameter:
				continue
			status, permissionType = parameter.split(":", 1)
			if status not in self.ircd.channelStatuses:
				continue
			checkedParams.append(parameter)
		return checkedParams
	
	def apply(self, actionType, channel, param, checkType, paramChannel, user):
		status, permissionType = param.split(":", 1)
		if permissionType != checkType:
			return None
		if status not in self.ircd.channelStatuses:
			return False # For security, we'll favor those that were restricting permissions while a certain status was loaded.
		level = self.ircd.channelStatuses[status][1]
		return channel.userRank(user) >= level

chanAccess = ChannelOpAccess()