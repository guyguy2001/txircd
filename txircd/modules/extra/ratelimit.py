from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import now, timestamp
from zope.interface import implements

class RateLimit(ModuleData):
	implements(IPlugin, IModuleData)

	name = "RateLimit"

	def actions(self):
		return [("commandpermission", 100, self.recvCommand)]

	def verifyConfig(self, config):
		if "ratelimit" in config:
			if not isinstance(config["ratelimit"], dict):
				raise ConfigValidationError("ratelimit", "value must be a dictionary")
			for key, value in config["ratelimit"].itemitems():
				if key not in ("limit", "kill_limit", "interval"):
					continue
				if not isinstance(value, int) or value < 0: # We might want to do some checking for insane values here
					raise ConfigValidationError("ratelimit", "value \"{}\" is an invalid number".format(key))

	def getConfig(self):
		config = {
			"limit": 60, # stop accepting commands after this many
			"kill_limit": 500, # disconnect the user after this many
			"interval": 60,
		}
		config.update(self.ircd.config.get("ratelimit", {}))
		return config

	def getPeriodData(self):
		"""Returns (period as integer, time to end of period)"""
		nowTS = timestamp(now())
		interval = self.getConfig()["interval"]
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
		rateData["messages"] += 1
		if rateData["messages"] > self.getConfig()["kill_limit"]:
			user.disconnect("Killed: Flooding")
			return False
		if rateData["messages"] > self.getConfig()["limit"]:
			# only send notice once per period
			if not rateData["noticeSent"]:
				user.sendMessage("NOTICE", ("You are sending too many messages (limit is {limit}/{interval:.2f}s). "
											"You cannot send any more messages for {timeToEnd:.2f} seconds."
										).format(timeToEnd=timeToEnd, **self.getConfig()))
				self.ircd.log.info("User {user.uuid} ({user.nick}) exceeded the message limit", user=user)
				rateData["noticeSent"] = True
			# we whitelist ping/pong to prevent ping timeouts
			if command not in ("PING", "PONG"):
				return False
		return None

rateLimit = RateLimit()