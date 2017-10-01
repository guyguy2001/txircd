from twisted.plugin import IPlugin
from txircd.channel import IRCChannel
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import isValidChannelName
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class AutoJoin(ModuleData):
	name = "AutoJoin"

	def actions(self):
		return [ ("welcome", 1, self.autoJoinChannels) ]

	def verifyConfig(self, config):
		if "client_join_on_connect" in config:
			if not isinstance(config["client_join_on_connect"], list):
				raise ConfigValidationError("client_join_on_connect", "value must be a list")
			for chanName in config["client_join_on_connect"]:
				if chanName[0] != "#":
					chanName = "#{}".format(chanName)
				if not isValidChannelName(chanName):
					raise ConfigValidationError("client_join_on_connect", "\"{}\" is an invalid channel name".format(chanName))

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