from txircd.utils import now, timestamp
from datetime import timedelta

class XLineBase(object):
	lineType = None
	lines = []
	
	def matchUser(self, user, context):
		self.expireLines()
		if not self.lineType:
			return False
		for lineData in self.lines:
			mask = lineData["mask"]
			if self.checkUserMatch(user, mask) and self.runComboActionUntilValue((("verifyxlinematch-{}".format(self.lineType), user, mask), ("verifyxlinematch", self.lineType, user, mask)), users=[user]) is not False:
				self.onUserMatch(user, context, lineData["reason"])
				return True
		return False
	
	def checkUserMatch(self, user, mask):
		pass
	
	def addLine(self, mask, durationSeconds, setter, reason):
		self.expireLines()
		if not self.lineType:
			return
		for lineData in self.lines:
			if mask == lineData["mask"]:
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
		for index, lineData in enumerate(self.lines):
			if lineData["mask"] == mask:
				del self.lines[index]
				return
	
	def onUserMatch(self, user, context, banReason):
		pass
	
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