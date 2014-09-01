from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements
import time


class RateLimit(ModuleData):
    implements(IPlugin, IModuleData)

    name = "RateLimit"

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def actions(self):
        return [("commandpermission", 100, self.recvCommand)]

    def getConfig(self):
        config = {
            "limit": 60,
            "interval": 60,
        }
        config.update(self.ircd.config.getWithDefault("ratelimit", {}))
        return config

    def getPeriodData(self):
        """Returns (period as integer, time to end of period)"""
        now = time.time()
        interval = self.getConfig()["interval"]
        period = int(now / interval)
        timeToEnd = (period + 1) * interval - now
        return period, timeToEnd

    def recvCommand(self, user, command, data):
        rateData = user.cache.setdefault("ratelimit-stats", {})
        thisPeriod, timeToEnd = self.getPeriodData()
        if rateData.get("period", None) != thisPeriod:
            # reset stats after each period
            rateData["messages"] = 0
            rateData["period"] = thisPeriod
            rateData["noticeSent"] = False
        if rateData["messages"] > self.getConfig()["limit"]:
            # only send notice once per period
            if not rateData["noticeSent"]:
                user.sendMessage("NOTICE", (":You are sending too many messages (limit is {limit}/{interval:.2f}s). "
                                            "You cannot send any more messages for {timeToEnd:.2f} seconds."
                                           ).format(timeToEnd=timeToEnd, **self.getConfig()))
                rateData["noticeSent"] = True
            return False
        rateData["messages"] += 1
        return None

rateLimit = RateLimit()
