from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements
from fnmatch import fnmatchcase

irc.ERR_CHANNOTALLOWED = "926"

class DenyChannels(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "DenyChannels"
	
	def actions(self):
		return [ ("joinpermission", 50, self.blockNonDenied) ]
	
	def blockNonDenied(self, channel, user):
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "channel-denied") is True:
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