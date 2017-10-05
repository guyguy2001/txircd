from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, List, Tuple

@implementer(IPlugin, IModuleData)
class StatusReport(ModuleData):
	name = "ChannelStatusReport"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("channelstatuses", 1, self.statuses) ]
	
	def statuses(self, channel: "IRCChannel", user: "IRCUser", requestingUser: "IRCUser") -> str:
		if user not in channel.users:
			return None
		if not channel.users[user]:
			return ""
		if not channel.users[user]["status"]:
			return ""
		return self.ircd.channelStatuses[channel.users[user]["status"][0]][0]

statuses = StatusReport()