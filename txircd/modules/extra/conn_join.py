from twisted.plugin import IPlugin
from twisted.python import log
from txircd.channel import InvalidChannelName, IRCChannel
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements
import logging

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
				try:
					channel = IRCChannel(self.ircd, chanName)
				except InvalidChannelName:
					log.msg("Invalid channel name {} in conn_join configuration".format(chanName), logLevel=logging.WARNING)
					continue
			user.joinChannel(channel)

autoJoin = AutoJoin()