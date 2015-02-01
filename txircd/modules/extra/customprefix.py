from twisted.plugin import IPlugin
from twisted.python import log
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements
import logging

class CustomPrefix(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)

	name = "CustomPrefix"
	prefixes = None

	def channelModes(self):
		modes = []
		self.prefixes = self.ircd.config.get("custom_prefixes", { "h": { "level": 50, "char": "%" }, "a": { "level": 150, "char": "&" }, "q" : { "level": 200, "char": "~" } })
		for prefix, prefixValue in self.prefixes.iteritems():
			try:
				statusLevel = int(prefixValue["level"])
				modes.append((prefix, ModeType.Status, self, statusLevel, prefixValue["char"]))
			except ValueError:
				log.msg("CustomPrefix: Prefix {} does not specify a valid level; skipping prefix".format(prefix), logLevel=logging.WARNING)
			except KeyError as e:
				log.msg("CustomPrefix: Prefix {} is missing {}; skipping prefix".format(prefix, e. message), logLevel=logging.WARNING)
		return modes

	def checkSet(self, channel, param):
		return param.split(",")
	
	def checkUnset(self, channel, param):
		return param.split(",")

	def fullUnload(self):
		for channel in self.ircd.channels.itervalues():
			for user, rank in channel.users.iteritems():
				for prefix in self.prefixes.iterkeys():
					if prefix in rank:
						channel.setModes(self.ircd.serverID, "-{}".format(prefix), [user.nick])

customPrefix = CustomPrefix()