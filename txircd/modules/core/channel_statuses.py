from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class StatusReport(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ChannelStatusReport"
	core = True
	
	def actions(self):
		return [ ("channelstatuses", 1, self.statuses) ]
	
	def statuses(self, channel, user, requestingUser):
		if user not in channel.users:
			return None
		if not channel.users[user]:
			return ""
		if not channel.users[user]["status"]:
			return ""
		return self.ircd.channelStatuses[channel.users[user]["status"][0]][0]

statuses = StatusReport()