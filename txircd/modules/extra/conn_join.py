from twisted.plugin import IPlugin
from txircd.channel import IRCChannel
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class AutoJoin(ModuleData):
	implements(IPlugin, IModuleData)

	name = "AutoJoin"

	def actions(self):
		return [ ("welcome", 1, self.autoJoinChannels) ]

	def autoJoinChannels(self, user):
		for chanName in self.ircd.config.get("client_join_on_connect", []):
			if chanName[0] != "#":
				chanName = "#{}".format(chanName)
			if chanName in self.ircd.channels:
				channel = self.ircd.channels[chanName]
			else:
				channel = IRCChannel(self.ircd, chanName)
			user.joinChannel(channel)

autoJoin = AutoJoin()