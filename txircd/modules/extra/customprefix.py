from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements

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
				self.ircd.log.warn("Custom prefix {prefix} does not specify a valid level; skipping prefix", prefix=prefix)
			except KeyError as e:
				self.ircd.log.warn("Custom prefix {prefix} is missing {missingKey}; skipping prefix", prefix=prefix, missingKey=e)
		return modes

	def checkSet(self, channel, param):
		return param.split(",")
	
	def checkUnset(self, channel, param):
		return param.split(",")

customPrefix = CustomPrefix()