from txircd.utils import ircLower, now, timestampStringFromTime, timestampStringFromTimeSeconds
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

class XLineBase(object):
	lineType = None
	propagateToServers = True
	burstQueuePriority = 50
	
	def initializeLineStorage(self) -> None:
		if "xlines" not in self.ircd.storage:
			self.ircd.storage["xlines"] = {}
		if self.lineType not in self.ircd.storage["xlines"]:
			self.ircd.storage["xlines"][self.lineType] = []
		self.expireLines()
	
	def matchUser(self, user: "IRCUser", data: Dict[Any, Any] = None) -> Optional[str]:
		if not self.lineType:
			return None
		if user.uuid[:3] != self.ircd.serverID:
			return None # The remote server should handle the users on that server
		self.expireLines()
		for lineData in self.ircd.storage["xlines"][self.lineType]:
			mask = lineData["mask"]
			if self.checkUserMatch(user, mask, data) and self.ircd.runComboActionUntilValue((("verifyxlinematch-{}".format(self.lineType), (user, mask, data)), ("verifyxlinematch", (self.lineType, user, mask, data))), users=[user]) is not False:
				return lineData["reason"]
		return None
	
	def checkUserMatch(self, user: "IRCUser", mask: str, data: Optional[Dict[Any, Any]]) -> bool:
		pass
	
	def addLine(self, mask: str, createdTime: datetime, durationSeconds: int, setter: str, reason: str, fromServer: "IRCServer" = None) -> bool:
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
		self.ircd.runActionStandard("addxline", self.lineType, mask, durationSeconds, setter, reason)
		if self.propagateToServers:
			self.ircd.broadcastToServers(fromServer, "ADDLINE", self.lineType, mask, setter, timestampStringFromTime(createdTime), str(durationSeconds), reason, prefix=self.ircd.serverID)
		return True
	
	def delLine(self, mask: str, setter: str, fromServer: "IRCServer" = None) -> bool:
		if not self.lineType:
			return False
		normalMask = self.normalizeMask(mask)
		for index, lineData in enumerate(self.ircd.storage["xlines"][self.lineType]):
			lineMask = self.normalizeMask(lineData["mask"])
			if normalMask == lineMask:
				del self.ircd.storage["xlines"][self.lineType][index]
				self.ircd.runActionStandard("delxline", self.lineType, mask, setter)
				if self.propagateToServers:
					self.ircd.broadcastToServers(fromServer, "DELLINE", self.lineType, mask, setter)
				return True
		return False
	
	def normalizeMask(self, mask: str) -> str:
		return ircLower(mask)
	
	def expireLines(self) -> None:
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
	
	def generateInfo(self) -> Dict[str, str]:
		if not self.lineType:
			return None
		self.expireLines()
		lineInfo = {}
		for lineData in self.ircd.storage["xlines"][self.lineType]:
			lineInfo[lineData["mask"]] = "{} {} {} :{}".format(timestampStringFromTimeSeconds(lineData["created"]), lineData["duration"], lineData["setter"], lineData["reason"])
		return lineInfo
	
	def handleServerAddParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 6:
			return None
		try:
			return {
				"linetype": params[0],
				"mask": params[1],
				"setter": params[2],
				"created": datetime.utcfromtimestamp(float(params[3])),
				"duration": int(params[4]),
				"reason": params[5]
			}
		except ValueError:
			return None
	
	def executeServerAddCommand(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if data["linetype"] != self.lineType:
			return False
		self.addLine(data["mask"], data["created"], data["duration"], data["setter"], data["reason"], server)
		return True
	
	def handleServerDelParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 3:
			return None
		return {
			"linetype": params[0],
			"mask": params[1],
			"setter": params[2]
		}
	
	def executeServerDelCommand(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if data["linetype"] != self.lineType:
			return False
		self.delLine(data["mask"], data["setter"], server)
		return True
	
	def burstLines(self, server: "IRCServer") -> None:
		if not self.lineType:
			return
		self.expireLines()
		if self.propagateToServers:
			for lineData in self.ircd.storage["xlines"][self.lineType]:
				server.sendMessage("ADDLINE", self.lineType, lineData["mask"], lineData["setter"], timestampStringFromTime(lineData["created"]), str(lineData["duration"]), lineData["reason"], prefix=self.ircd.serverID)