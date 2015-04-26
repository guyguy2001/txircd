from txircd.utils import ircLower, now, timestamp
from datetime import datetime, timedelta

class XLineBase(object):
	lineType = None
	propagateToServers = True
	
	def initializeLineStorage(self):
		if "xlines" not in self.ircd.storage:
			self.ircd.storage["xlines"] = {}
		if self.lineType not in self.ircd.storage["xlines"]:
			self.ircd.storage["xlines"][self.lineType] = []
		self.expireLines()
	
	def matchUser(self, user, data = None):
		if not self.lineType:
			return None
		self.expireLines()
		for lineData in self.ircd.storage["xlines"][self.lineType]:
			mask = lineData["mask"]
			if self.checkUserMatch(user, mask, data) and self.ircd.runComboActionUntilValue((("verifyxlinematch-{}".format(self.lineType), user, mask, data), ("verifyxlinematch", self.lineType, user, mask, data)), users=[user]) is not False:
				return lineData["reason"]
		return None
	
	def checkUserMatch(self, user, mask, data):
		pass
	
	def addLine(self, mask, createdTime, durationSeconds, setter, reason, fromServer = None):
		if not self.lineType:
			return False
		self.expireLines()
		normalMask = self.normalizeMask(mask)
		lines = self.ircd.storage["xlines"][self.lineType]
		for lineData in lines:
			lineMask = self.normalizeMask(lineData["mask"])
			if normalMask == lineMask:
				return False
		lines.append({
			"mask": mask,
			"created": createdTime,
			"duration": durationSeconds,
			"setter": setter,
			"reason": reason
		})
		if self.propagateToServers:
			self.ircd.broadcastToServers(fromServer, "ADDLINE", self.lineType, mask, setter, str(timestamp(createdTime)), str(durationSeconds), reason, prefix=self.ircd.serverID)
		return True
	
	def delLine(self, mask):
		if not self.lineType:
			return False
		normalMask = self.normalizeMask(mask)
		for index, lineData in enumerate(self.ircd.storage["xlines"][self.lineType]):
			lineMask = self.normalizeMask(mask)
			if normalMask == lineMask:
				del self.ircd.storage["xlines"][self.lineType][index]
				return True
		return False
	
	def normalizeMask(self, mask):
		return ircLower(mask)
	
	def expireLines(self):
		if not self.lineType:
			return
		currentTime = now()
		expiredLines = []
		lines = self.ircd.storage["xlines"][self.lineType]
		for lineData in lines:
			durationSeconds = lineData["duration"]
			if not durationSeconds:
				continue
			duration = timedelta(seconds=lineData["duration"])
			expireTime = lineData["created"] + duration
			if expireTime < currentTime:
				expiredLines.append(lineData)
		for lineData in expiredLines:
			lines.remove(lineData)
	
	def generateInfo(self):
		if not self.lineType:
			return None
		lineInfo = {}
		for lineData in self.ircd.storage["xlines"][self.lineType]:
			lineInfo[lineData["mask"]] = "{} {} {} :{}".format(timestamp(lineData["created"]), lineData["duration"], lineData["setter"], lineData["reason"])
		return lineInfo
	
	def handleServerAddParams(self, server, params, prefix, tags):
		if len(params) != 6:
			return None
		try:
			return {
				"linetype": params[0],
				"mask": params[1],
				"setter": params[2],
				"created": params[3],
				"duration": int(params[4]),
				"reason": params[5]
			}
		except ValueError:
			return None
	
	def executeServerAddCommand(self, server, data):
		if data["linetype"] != self.lineType:
			return None
		self.addLine(data["mask"], datetime.utcfromtimestamp(data["created"]), data["duration"], data["setter"], data["reason"], server)
		return True
	
	def handleServerDelParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		return {
			"linetype": params[0],
			"mask": params[1]
		}
	
	def executeServerDelCommand(self, server, data):
		if data["linetype"] != self.lineType:
			return None
		self.delLine(data["mask"])
		return True
	
	def burstLines(self, server):
		if not self.lineType:
			return
		self.expireLines()
		for lineData in self.ircd.storage["xlines"][self.lineType]:
			server.sendMessage("ADDLINE", self.lineType, lineData["mask"], lineData["setter"], str(timestamp(lineData["created"])), str(durationSeconds), reason, prefix=self.ircd.serverID)