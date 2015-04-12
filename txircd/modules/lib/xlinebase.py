from txircd.utils import ircLower, now, timestamp
from datetime import datetime, timedelta

class XLineBase(object):
	lineType = None
	propagateToServers = True
	
	def matchUser(self, user):
		self.expireLines()
		if not self.lineType:
			return None
		for lineData in self.ircd.storage["xlines"][self.lineType]:
			mask = lineData["mask"]
			if self.checkUserMatch(user, mask) and self.runComboActionUntilValue((("verifyxlinematch-{}".format(self.lineType), user, mask), ("verifyxlinematch", self.lineType, user, mask)), users=[user]) is not False:
				return lineData["reason"]
		return None
	
	def checkUserMatch(self, user, mask):
		pass
	
	def addLine(self, mask, createdTime, durationSeconds, setter, reason, fromServer = None):
		self.expireLines()
		if not self.lineType:
			return False
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
			self.ircd.broadcastToServers(fromServer, "ADDLINE", self.lineType, mask, setter, str(timestamp(createdTime)), durationSeconds, reason, prefix=self.ircd.serverID)
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
		currentTime = now()
		expiredLines = []
		lines = self.ircd.storage["xlines"][self.lineType]
		for lineData in lines:
			duration = timedelta(seconds=lineData["duration"])
			expireTime = currentTime + duration
			if expireTime < currentTime:
				expiredLines.append(lineData)
		for lineData in expiredLines:
			lines.remove(lineData)
	
	def generateInfo(self):
		lineInfo = {}
		for lineData in self.ircd.storage["xlines"][self.lineType]:
			lineInfo[lineData["mask"]] = "{} {} {} :{}".format(timestamp(lineData["created"]), lineData["duration"], lineData["setter"], lineData["reason"])
		return lineInfo
	
	def handleServerParams(self, server, params, prefix, tags):
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
	
	def executeServerCommand(self, server, data):
		if data["linetype"] != self.lineType:
			return None
		self.addLine(data["mask"], datetime.utcfromtimestamp(data["created"]), data["duration"], data["setter"], data["reason"], server)
		return True