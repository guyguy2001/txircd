from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, splitMessage
from zope.interface import implements

irc.RPL_MONONLINE = "730"
irc.RPL_MONOFFLINE = "731"
irc.RPL_MONLIST = "732"
irc.RPL_ENDOFMONLIST = "733"
irc.ERR_MONLISTFULL = "734"
irc.RPL_KEYVALUE = "761"
irc.RPL_METADATAEND = "762"

class Monitor(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "Monitor"
	
	def actions(self):
		return [ ("capabilitylist", 10, self.addCapability),
		         ("welcome", 1, self.reportNewUser),
		         ("remoteregister", 1, self.reportNewUser),
		         ("changenick", 1, self.reportNickChangeUser),
		         ("remotechangenick", 1, self.reportNickChangeUser),
		         ("quit", 1, self.reportGoneUser),
		         ("remotequit", 1, self.reportGoneUser),
		         ("addusercap", 1, self.userSubMetadata),
		         ("usermetadataupdate", 1, self.notifyUserMetadataChange),
		         ("channelmetadataupdate", 1, self.notifyChannelMetadataChange),
		         ("buildisupport", 1, self.buildISupport) ]
	
	def userCommands(self):
		return [ ("MONITOR", 1, self) ]
	
	def load(self):
		self.targetIndex = CaseInsensitiveDictionary()
		# We'll run a cleaner every minute. The reason we do this is that, since there can be multiple
		# notified users for a target, the index is implemented as a CaseInsensitiveDictionary pointing
		# to WeakSets as opposed to simply a CaseInsensitiveDictionary(WeakValueDictionary). Because of
		# this, we'll need to check for empty WeakSets on occasion and garbage-collect them to prevent
		# memory getting full.
		self.indexCleaner = LoopingCall(self.cleanIndex)
		self.indexCleaner.start(60, now=False)
		if "unloading-monitor" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-monitor"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("metadata-notify")
	
	def unload(self):
		if self.indexCleaner.running:
			self.indexCleaner.stop()
		self.ircd.dataCache["unloading-monitor"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-monitor"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("metadata-notify")
	
	def verifyConfig(self, config):
		if "monitor_limit" not in config:
			config["monitor_limit"] = None
			return
		if not isinstance(config["monitor_limit"], int) or config["monitor_limit"] < 0:
			raise ConfigValidationError("monitor_limit", "invalid number")
	
	def addCapability(self, user, capList):
		capList.append("metadata-notify")
	
	def reportNewUser(self, user):
		self._doNotify(user.nick, irc.RPL_MONONLINE)
	
	def reportNickChangeUser(self, user, oldNick, fromServer):
		self._doNotify(oldNick, irc.RPL_MONOFFLINE)
		self._doNotify(user.nick, irc.RPL_MONONLINE)
	
	def reportGoneUser(self, user, reason):
		if user.isRegistered():
			self._doNotify(user.nick, irc.RPL_MONOFFLINE)
	
	def _doNotify(self, nick, numeric):
		if nick in self.targetIndex:
			for notifyUser in self.targetIndex[nick]:
				notifyUser.sendMessage(numeric, nick)
	
	def userSubMetadata(self, user, capability, value):
		if capability != "metadata-notify":
			return
		self.sendUserMetadata(user, user)
		if "monitor" in user.cache:
			for target in user.cache["monitor"]:
				if target in self.ircd.userNicks:
					targetUser = self.ircd.users[self.ircd.userNicks[target]]
					self.sendUserMetadata(targetUser, user)
	
	def notifyUserMetadataChange(self, user, key, oldValue, value, visibility, setByUser, fromServer):
		sentToUsers = set()
		if not setByUser and ("capabilities" in user.cache and "metadata-notify" in user.cache["capabilities"]) and user.canSeeMetadataVisibility(visibility):
			# Technically, the spec excludes "changes made by the clients themselves" from notification. However,
			# since we don't know WHICH user changed the metadata, we'll exclude all sets by users and hope that
			# nobody's actually changing someone else's metadata (would only be opers).
			if value is None:
				user.sendMessage("METADATA", key, visibility, to=user.nick)
			else:
				user.sendMessage("METADATA", key, visibility, value, to=user.nick)
			sentToUsers.add(user)
		if user.nick in self.targetIndex:
			for monitoringUser in self.targetIndex[user.nick]:
				if monitoringUser in sentToUsers:
					continue
				if "capabilities" in monitoringUser.cache and "metadata-notify" in monitoringUser.cache["capabilities"] and monitoringUser.canSeeMetadataVisibility(visibility):
					if value is None:
						monitoringUser.sendMessage("METADATA", key, visibility, to=user.nick)
					else:
						monitoringUser.sendMessage("METADATA", key, visibility, value, to=user.nick)
					sentToUsers.add(monitoringUser)
		for channel in user.channels:
			for inChannelUser in channel.users.iterkeys():
				if inChannelUser in sentToUsers:
					continue
				if "capabilities" in inChannelUser.cache and "metadata-notify" in inChannelUser.cache["capabilities"] and inChannelUser.canSeeMetadataVisibility(visibility):
					if value is None:
						inChannelUser.sendMessage("METADATA", key, visibility, to=user.nick)
					else:
						inChannelUser.sendMessage("METADATA", key, visibility, value, to=user.nick)
					sentToUsers.add(inChannelUser)
	
	def notifyChannelMetadataChange(self, channel, key, oldValue, value, visibility, setByUser, fromServer):
		for user in channel.users.iterkeys():
			if "capabilities" in user.cache and "metadata-notify" in user.cache["capabilities"] and user.canSeeMetadataVisibility(visibility):
				if value is None:
					user.sendMessage("METADATA", key, visibility, to=channel.name)
				else:
					user.sendMessage("METADATA", key, visibility, value, to=channel.name)
	
	def buildISupport(self, data):
		data["MONITOR"] = self.ircd.config["monitor_limit"]
	
	def cleanIndex(self):
		removeKeys = []
		for target, notifyList in self.targetIndex.iteritems():
			if not notifyList:
				removeKeys.append(target)
		for target in removeKeys:
			del self.targetIndex[target]
	
	def sendUserMetadata(self, user, sendToUser):
		metadataList = user.metadataList()
		for key, value, visibility, setByUser in metadataList:
			if sendToUser.canSeeMetadataVisibility(visibility):
				sendToUser.sendMessage(irc.RPL_KEYVALUE, user.nick, key, visibility, value)
		sendToUser.sendMessage(irc.RPL_METADATAEND, "end of metadata")
	
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
					onlineUserList.append(self.ircd.users[self.ircd.userNicks[target]])
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