from txircd.utils import ircLower, now, timestamp
from datetime import timedelta

class XLineBase(object):
	lineType = None
	lines = []
	
	def matchUser(self, user):
		self.expireLines()
		if not self.lineType:
			return None
		for lineData in self.lines:
			mask = lineData["mask"]
			if self.checkUserMatch(user, mask) and self.runComboActionUntilValue((("verifyxlinematch-{}".format(self.lineType), user, mask), ("verifyxlinematch", self.lineType, user, mask)), users=[user]) is not False:
				return lineData["reason"]
		return None
	
	def checkUserMatch(self, user, mask):
		pass
	
	def addLine(self, mask, durationSeconds, setter, reason):
		self.expireLines()
		if not self.lineType:
			return
		normalMask = self.normalizeMask(mask)
		for lineData in self.lines:
			lineMask = self.normalizeMask(lineData["mask"])
			if normalMask == lineMask:
				return 
		self.lines.append({
			"mask": mask,
			"created": now(),
			"duration": durationSeconds,
			"setter": setter,
			"reason": reason
		})
	
	def delLine(self, mask):
		if not self.lineType:
			return
		normalMask = self.normalizeMask(mask)
		for index, lineData in enumerate(self.lines):
			lineMask = self.normalizeMask(mask)
			if normalMask == lineMask:
				del self.lines[index]
				return
	
	def normalizeMask(self, mask):
		return ircLower(mask)
	
	def expireLines(self):
		currentTime = now()
		expiredLines = []
		for lineData in self.lines:
			duration = timedelta(seconds=lineData["duration"])
			expireTime = currentTime + duration
			if expireTime < currentTime:
				expiredLines.append(lineData)
		for lineData in expiredLines:
			self.lines.remove(lineData)
	
	def generateInfo(self):
		lineInfo = {}
		for lineData in self.lines:
			lineInfo[lineData["mask"]] = "{} {} {} :{}".format(timestamp(lineData["created"]), lineData["duration"], lineData["setter"], lineData["reason"])
		return lineInfo