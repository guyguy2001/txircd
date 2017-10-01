from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import now
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class StatsUptime(ModuleData):
	name = "StatsUptime"

	def actions(self):
		return [ ("statsruntype-uptime", 10, self.displayUptime) ]

	def displayUptime(self):
		uptime = now() - self.ircd.startupTime
		return {
			self.ircd.name: "Server up {}".format(uptime if uptime.days > 0 else "0 days, {}".format(uptime))
		}

statsUptime = StatsUptime()