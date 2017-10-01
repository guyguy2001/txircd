from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import now, timestamp
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class RateLimit(ModuleData):
	name = "RateLimit"
	
	def actions(self):
		return [ ("commandpermission", 100, self.recvCommand) ]
	
	def verifyConfig(self, config):
		if "rate_soft_limit" in config:
			if not isinstance(config["rate_soft_limit"], int) or config["rate_soft_limit"] < 0:
				raise ConfigValidationError("rate_soft_limit", "invalid number")
			if config["rate_soft_limit"] == 0:
				self.ircd.logConfigValidationWarning("rate_soft_limit", "a value of 0 will block everything", 1)
				config["rate_soft_limit"] = 1
		else:
			config["rate_soft_limit"] = 60
		
		if "rate_kill_limit" in config:
			if not isinstance(config["rate_kill_limit"], int) or config["rate_kill_limit"] < 0:
				raise ConfigValidationError("rate_kill_limit", "invalid number")
			if config["rate_kill_limit"] == 0:
				self.ircd.logConfigValidationWarning("rate_kill_limit", "a value of 0 will kill everyone; what's the point of having a server?", 1)
				config["rate_kill_limit"] = 1
		else:
			config["rate_kill_limit"] = 500
		
		if "rate_interval" in config:
			if not isinstance(config["rate_interval"], int) or config["rate_interval"] < 0:
				raise ConfigValidationError("rate_interval", "invalid number")
		else:
			config["rate_interval"] = 60
	
	def getPeriodData(self):
		"""Returns (period as integer, time to end of period)"""
		nowTS = timestamp(now())
		interval = self.ircd.config["rate_interval"]
		period = int(nowTS / interval)
		timeToEnd = (period + 1) * interval - nowTS
		return period, timeToEnd
	
	def recvCommand(self, user, command, data):
		rateData = user.cache.setdefault("ratelimit-stats", {})
		thisPeriod, timeToEnd = self.getPeriodData()
		if rateData.get("period", None) != thisPeriod:
			# reset stats after each period
			rateData["messages"] = 0
			rateData["period"] = thisPeriod
			rateData["noticeSent"] = False
		killLimit = self.ircd.config["rate_kill_limit"]
		rateData["messages"] += 1
		if rateData["messages"] > killLimit:
			user.disconnect("Killed: Flooding")
			return False
		softLimit = self.ircd.config["rate_soft_limit"]
		if rateData["messages"] > softLimit:
			# only send notice once per period
			if not rateData["noticeSent"]:
				user.sendMessage("NOTICE", ("You are sending too many messages (limit is {limit}/{interval:.2f}s). "
					"You cannot send any more messages for {timeToEnd:.2f} seconds."
					).format(limit=softLimit, interval=self.ircd.config["rate_interval"], timeToEnd=timeToEnd))
				self.ircd.log.info("User {user.uuid} ({user.nick}) exceeded the message limit", user=user)
				rateData["noticeSent"] = True
			# we whitelist ping/pong to prevent ping timeouts
			if command not in ("PING", "PONG"):
				return False
		return None

rateLimit = RateLimit()