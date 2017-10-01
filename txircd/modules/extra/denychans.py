from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from fnmatch import fnmatchcase

irc.ERR_CHANNOTALLOWED = "926"

@implementer(IPlugin, IModuleData)
class DenyChannels(ModuleData):
	name = "DenyChannels"
	
	def actions(self):
		return [ ("joinpermission", 50, self.blockNonDenied) ]

	def verifyConfig(self, config):
		for option in ("deny_channels", "allow_channels"):
			if option in config:
				if not isinstance(config[option], list):
					raise ConfigValidationError(option, "value must be a list")
				for chanName in config[option]:
					if not isinstance(chanName, basestring) or not chanName:
						raise ConfigValidationError(option, "\"{}\" is an invalid channel name".format(chanName))
	
	def blockNonDenied(self, channel, user):
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "channel-denied", users=[user]) is True:
			return None
		deniedChannels = self.ircd.config.get("deny_channels", [])
		allowedChannels = self.ircd.config.get("allow_channels", [])
		for name in allowedChannels:
			if fnmatchcase(channel.name, name):
				return None
		for name in deniedChannels:
			if fnmatchcase(channel.name, name):
				user.sendMessage(irc.ERR_CHANNOTALLOWED, channel.name, "Channel {} is forbidden".format(channel.name))
				return False
		return None

denyChans = DenyChannels()