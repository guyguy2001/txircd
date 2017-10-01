from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, splitMessage
from zope.interface import implementer

irc.RPL_MONONLINE = "730"
irc.RPL_MONOFFLINE = "731"
irc.RPL_MONLIST = "732"
irc.RPL_ENDOFMONLIST = "733"
irc.ERR_MONLISTFULL = "734"
irc.RPL_KEYVALUE = "761"
irc.RPL_METADATAEND = "762"

@implementer(IPlugin, IModuleData, ICommand)
class Monitor(ModuleData, Command):
	name = "Monitor"
	
	def actions(self):
		return [ ("welcome", 1, self.reportNewUser),
		         ("remoteregister", 1, self.reportNewUser),
		         ("changenick", 1, self.reportNickChangeUser),
		         ("remotechangenick", 1, self.reportNickChangeUser),
		         ("quit", 1, self.reportGoneUser),
		         ("remotequit", 1, self.reportGoneUser),
		         ("buildisupport", 1, self.buildISupport) ]
	
	def userCommands(self):
		return [ ("MONITOR", 1, self) ]
	
	def load(self):
		self.ircd.dataCache["monitor-index"] = CaseInsensitiveDictionary()
		# We'll run a cleaner every minute. The reason we do this is that, since there can be multiple
		# notified users for a target, the index is implemented as a CaseInsensitiveDictionary pointing
		# to WeakSets as opposed to simply a CaseInsensitiveDictionary(WeakValueDictionary). Because of
		# this, we'll need to check for empty WeakSets on occasion and garbage-collect them to prevent
		# memory getting full.
		self.indexCleaner = LoopingCall(self.cleanIndex)
		self.indexCleaner.start(60, now=False)
	
	def unload(self):
		if self.indexCleaner.running:
			self.indexCleaner.stop()
	
	def verifyConfig(self, config):
		if "monitor_limit" not in config:
			config["monitor_limit"] = None
			return
		if not isinstance(config["monitor_limit"], int) or config["monitor_limit"] < 0:
			raise ConfigValidationError("monitor_limit", "invalid number")
	
	def reportNewUser(self, user):
		self._doNotify(user.nick, irc.RPL_MONONLINE)
	
	def reportNickChangeUser(self, user, oldNick, fromServer):
		self._doNotify(oldNick, irc.RPL_MONOFFLINE)
		self._doNotify(user.nick, irc.RPL_MONONLINE)
	
	def reportGoneUser(self, user, reason, fromServer):
		if user.isRegistered():
			self._doNotify(user.nick, irc.RPL_MONOFFLINE)
	
	def _doNotify(self, nick, numeric):
		if nick in self.ircd.dataCache["monitor-index"]:
			for notifyUser in self.ircd.dataCache["monitor-index"][nick]:
				notifyUser.sendMessage(numeric, nick)
	
	def buildISupport(self, data):
		data["MONITOR"] = self.ircd.config["monitor_limit"]
	
	def cleanIndex(self):
		removeKeys = []
		for target, notifyList in self.ircd.dataCache["monitor-index"].items():
			if not notifyList:
				removeKeys.append(target)
		for target in removeKeys:
			del self.ircd.dataCache["monitor-index"][target]
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendSingleError("MonitorParams", irc.ERR_NEEDMOREPARAMS, "MONITOR", "Not enough parameters")
			return None
		subcmd = params[0]
		if subcmd in ("+", "-"):
			if len(params) < 2:
				user.sendSingleError("Monitor+Params", irc.ERR_NEEDMOREPARAMS, "MONITOR", "Not enough parameters")
				return None
			nickList = params[1].split(",")
			return {
				"subcmd": subcmd,
				"targets": nickList
			}
		if subcmd in ("C", "L", "S"):
			return {
				"subcmd": subcmd
			}
		user.sendSingleError("MonitorBadSubcmd", irc.ERR_UNKNOWNCOMMAND, "MONITOR", "Unknown subcommand: {}".format(subcmd))
		return None
	
	def execute(self, user, data):
		subcmd = data["subcmd"]
		if subcmd == "+":
			monitorLimit = self.ircd.config["monitor_limit"]
			newTargets = data["targets"]
			if "monitor" not in user.cache:
				user.cache["monitor"] = set()
			if monitorLimit is not None and (len(user.cache["monitor"]) + len(newTargets)) > monitorLimit:
				user.sendMessage(irc.ERR_MONLISTFULL, monitorLimit, ",".join(newTargets), "Monitor list is full.")
				return True
			onlineList = []
			onlineUserList = []
			offlineList = []
			userMonitorList = user.cache["monitor"]
			for target in newTargets:
				if target in userMonitorList:
					continue
				userMonitorList.add(target)
				if target in self.ircd.userNicks:
					onlineList.append(target)
					onlineUserList.append(self.ircd.userNicks[target])
				else:
					offlineList.append(target)
			if onlineList:
				onlineLines = splitMessage(",".join(onlineList), 400, ",")
				for line in onlineLines:
					user.sendMessage(irc.RPL_MONONLINE, line)
			if offlineList:
				offlineLines = splitMessage(",".join(offlineList), 400, ",")
				for line in offlineLines:
					user.sendMessage(irc.RPL_MONOFFLINE, line)
			if "capabilities" in user.cache and "metadata-notify" in user.cache["capabilities"]:
				for targetUser in onlineUserList:
					self.sendUserMetadata(targetUser, user)
			return True
		if subcmd == "-":
			if "monitor" not in user.cache:
				return True
			userMonitorList = user.cache["monitor"]
			for target in data["targets"]:
				userMonitorList.discard(target)
			return True
		if subcmd == "C":
			if "monitor" in user.cache:
				del user.cache["monitor"]
			return True
		if subcmd == "L":
			if "monitor" not in user.cache:
				user.sendMessage(irc.RPL_ENDOFMONLIST, "End of MONITOR list")
				return True
			listLines = splitMessage(",".join(user.cache["monitor"]), 400, ",")
			for line in listLines:
				user.sendMessage(irc.RPL_MONLIST, line)
			user.sendMessage(irc.RPL_ENDOFMONLIST, "End of MONITOR list")
			return True
		if subcmd == "S":
			if "monitor" not in user.cache:
				return True
			onlineList = []
			offlineList = []
			for target in user.cache["monitor"]:
				if target in self.ircd.userNicks:
					onlineList.append(target)
				else:
					offlineList.append(target)
			onlineLines = splitMessage(",".join(onlineList), 400, ",")
			for line in onlineLines:
				user.sendMessage(irc.RPL_MONONLINE, line)
			offlineLines = splitMessage(",".join(offlineList), 400, ",")
			for line in offlineLines:
				user.sendMessage(irc.RPL_MONOFFLINE, line)
			return True
		return None

monitor = Monitor()