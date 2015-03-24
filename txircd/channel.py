from twisted.words.protocols import irc
from txircd.utils import isValidChannelName, ModeType, now
from weakref import WeakKeyDictionary

class IRCChannel(object):
	def __init__(self, ircd, name):
		if not isValidChannelName(name):
			raise InvalidChannelName
		self.ircd = ircd
		self.name = name[:64]
		self.users = WeakKeyDictionary()
		self.modes = {}
		self.existedSince = now()
		self.topic = ""
		self.topicSetter = ""
		self.topicTime = now()
		self.metadata = {
			"server": {},
			"user": {},
			"client": {},
			"ext": {},
			"private": {}
		}
		self.cache = {}
	
	def sendUserMessage(self, command, *params, **kw):
		if "to" not in kw:
			kw["to"] = self.name
		if kw["to"] is None:
			del kw["to"]
		userList = [u for u in self.users.iterkeys() if u.uuid[:3] == self.ircd.serverID]
		if "skip" in kw:
			for u in kw["skip"]:
				if u in userList:
					userList.remove(u)
		kw["users"] = userList
		kw["channels"] = [self]
		for user in userList:
			user.sendMessage(command, *params, **kw)
	
	def sendServerMessage(self, command, *params, **kw):
		servers = set()
		for user in self.users.iterkeys():
			if user.uuid[:3] != self.ircd.serverID:
				servers.add(self.ircd.servers[user.uuid[:3]])
		if "skipall" in kw:
			for s in kw["skipall"]:
				servers.discard(s)
		localServers = set()
		for server in servers:
			nearHop = server
			while nearHop.nextClosest != self.ircd.serverID:
				nearHop = self.ircd.servers[nearHop.nextClosest]
			localServers.add(nearHop)
		if "skiplocal" in kw:
			for s in kw["skiplocal"]:
				localServers.discard(s)
		for server in localServers:
			server.sendMessage(command, *params, **kw)
	
	def setTopic(self, topic, setter):
		if setter in self.ircd.users:
			source = self.ircd.users[setter].hostmask()
		elif setter == self.ircd.serverID:
			source = self.ircd.name
		elif setter in self.ircd.servers:
			source = self.ircd.servers[setter].name
		else:
			return False
		oldTopic = self.topic
		self.topic = topic
		self.topicSetter = source
		self.topicTime = now()
		self.ircd.runActionStandard("topic", self, setter, oldTopic, channels=[self])
		return True
	
	def setMetadata(self, namespace, key, value = None, fromServer = None):
		if namespace not in self.metadata:
			return
		oldValue = None
		if key in self.metadata[namespace]:
			oldValue = self.metadata[namespace][key]
		if oldValue == value:
			return
		if value is None:
			del self.metadata[namespace][key]
		else:
			self.metadata[namespace][key] = value
		self.ircd.runActionStandard("channelmetadataupdate", self, namespace, key, value, channels=[self])
	
	def setModes(self, modes, defaultSource):
		modeChanges = []
		defaultSourceName = self._sourceName(defaultSource)
		if defaultSourceName is None:
			raise ValueError ("Source must be a valid user or server ID.")
		for modeData in modes:
			mode = modeData[1]
			if mode not in self.ircd.channelModeTypes:
				continue
			modeType = self.ircd.channelModeTypes[mode]
			adding = modeData[0]
			if modeType in (ModeType.List, ModeType.ParamOnUnset, ModeType.Param, ModeType.Status):
				param = modeData[2]
			else:
				param = None
			if modeType == ModeType.List:
				dataCount = len(modeData)
				if dataCount >= 4:
					setBy = modeData[3]
				else:
					setBy = defaultSourceName
				if dataCount >= 5:
					setTime = modeData[4]
				else:
					setTime = now()
			if modeType == ModeType.Status:
				if adding:
					paramList = self.ircd.channelStatuses[mode][2].checkSet(self, param)
				else:
					paramList = self.ircd.channelStatuses[mode][2].checkUnset(self, param)
			else:
				if adding:
					paramList = self.ircd.channelModes[modeType][mode].checkSet(self, param)
				else:
					paramList = self.ircd.channelModes[modeType][mode].checkUnset(self, param)
			if paramList is None:
				continue
			
			for parameter in paramList:
				if self._applyMode(adding, modeType, mode, parameter, setBy, setTime):
					modeChanges.append((adding, mode, parameter, setBy, setTime))
		
		self._notifyModeChanges(modeChanges, defaultSource, defaultSourceName)
		return modeChanges
	
	def setModesByUser(self, user, modes, params, override = False):
		adding = True
		changes = []
		setBy = self._sourceName(user.uuid)
		setTime = now()
		for mode in modes:
			if len(changes) >= 20:
				break
			if mode == "+":
				adding = True
				continue
			if mode == "-":
				adding = False
				continue
			if mode not in self.ircd.channelModeTypes:
				user.sendMessage(irc.ERR_UNKNOWNMODE, mode, "is unknown mode char to me")
				continue
			modeType = self.ircd.channelModeTypes[mode]
			param = None
			if modeType in (ModeType.List, ModeType.ParamOnUnset, ModeType.Status) or (adding and modeType == ModeType.Param):
				try:
					param = params.pop(0)
				except IndexError:
					if modeType == ModeType.List:
						self.ircd.channelModes[modeType][mode].showListParams(user, self)
					continue
			if modeType == ModeType.Status:
				if adding:
					paramList = self.ircd.channelStatuses[mode][2].checkSet(self, param)
				else:
					paramList = self.ircd.channelStatuses[mode][2].checkUnset(self, param)
			else:
				if adding:
					paramList = self.ircd.channelModes[modeType][mode].checkSet(self, param)
				else:
					paramList = self.ircd.channelModes[modeType][mode].checkUnset(self, param)
			if paramList is None:
				continue
			
			for parameter in paramList:
				if len(changing) >= 20:
					break
				if not override and self.ircd.runActionUntilValue("modepermission-channel-{}".format(mode), self, user, adding, parameter, users=[user], channels=[self]) is False:
					continue
				if adding:
					if modeType == ModeType.Status:
						try:
							targetUser = self.ircd.users[self.ircd.userNicks[parameter]]
						except KeyError:
							continue
						if targetUser not in self.users:
							continue
						if mode in self.users[targetUser]["status"]:
							continue
						statusLevel = self.ircd.channelStatuses[mode][1]
						if not override and self.userRank(user) < statusLevel and not self.ircd.runActionUntilValue("channelstatusoverride", self, user, mode, parameter, users=[user], channels=[self]):
							user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, self.name, "You do not have permission to set channel mode +{}".format(mode))
							continue
						parameter = targetUser.uuid
					elif modeType == ModeType.List:
						if mode in self.modes and len(self.modes[mode]) > self.ircd.config.get("channel_list_limit", 128):
							user.sendMessage(irc.ERR_BANLISTFULL, self.name, parameter, "Channel +{} list is full".format(mode))
							continue
				else:
					if modeType == ModeType.Status:
						try:
							targetUser = self.ircd.users[self.ircd.userNicks[parameter]]
						except KeyError:
							continue
						if mode not in self.users[targetUser]:
							continue
						statusLevel = self.ircd.channelStatuses[mode][1]
						if not override and self.userRank(user) < statusLevel and not self.ircd.runActionUntilValue("channelstatusoverride", self, user, mode, parameter, users=[user], channels=[self]):
							user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, self.name, "You do not have permission to set channel mode -{}".format(mode))
							continue
						parameter = targetUser.uuid
				if self._applyMode(adding, modeType, mode, parameter, setBy, setTime):
					changes.append((adding, mode, parameter, setBy, setTime))
		self._notifyModeChanges(changes, user.uuid, setBy)
		return changes
	
	def _applyMode(self, adding, modeType, mode, parameter, setBy, setTime):
		if len(parameter) > 255:
			return False
		if " " in parameter:
			return False
		
		if adding:
			if modeType == ModeType.Status:
				try:
					targetUser = self.ircd.users[parameter]
				except KeyError:
					return False
				if targetUser not in self.users:
					return False
				if mode in self.users[targetUser]:
					return False
				statusLevel = self.ircd.channelStatuses[mode][1]
				targetStatus = self.users[targetUser]["status"]
				for index, rank in enumerate(targetStatus):
					if self.ircd.channelStatuses[rank][1] < statusLevel:
						statusList = list(targetStatus)
						statusList.insert(index, mode)
						self.users[targetUser]["status"] = "".join(statusList)
						return True
				self.users[targetUser]["status"] += mode
				return True
			if modeType == ModeType.List:
				if mode in self.modes:
					if len(self.modes[mode]) > self.ircd.config.get("channel_list_limit", 128):
						return False
					for paramData in self.modes[mode]:
						if parameter == paramData[0]:
							return False
				else:
					self.modes[mode] = []
				self.modes[mode].append((parameter, setBy, setTime))
				return True
			if mode in self.modes and self.modes[mode] == parameter:
				return False
			self.modes[mode] = parameter
			return True
		
		if modeType == ModeType.Status:
			try:
				targetUser = self.ircd.users[parameter]
			except KeyError:
				return False
			if targetUser not in self.users:
				return False
			if mode not in self.users[targetUser]["status"]:
				return False
			self.users[targetUser]["status"] = self.users[targetUser]["status"].replace(mode, "")
			return True
		if modeType == ModeType.List:
			if mode not in self.modes:
				return False
			for index, paramData in self.modes[mode]:
				if paramData[0] == parameter:
					del self.modes[mode][index]
					break
			else:
				return False
			if not self.modes[mode]:
				del self.modes[mode]
			return True
		if mode not in self.modes:
			return False
		if modeType == ModeType.ParamOnUnset and parameter != self.modes[mode]:
			return False
		del self.modes[mode]
		return True
	
	def _notifyModeChanges(self, modeChanges, source, sourceName):
		if not modeChanges:
			return
		channelUsers = []
		for user in self.users.iterkeys():
			if user.uuid[:3] == self.ircd.serverID:
				channelUsers.append(user)
		for change in modeChanges:
			self.ircd.runActionStandard("modechange-channel-{}".format(change[1]), self, change[3], change[0], change[2], channels=[self])
		self.ircd.runActionProcessing("modemessage-channel", channelUsers, self, source, sourceName, modeChanges, users=channelUsers, channels=[self])
		self.ircd.runActionStandard("modechanges-channel", self, source, sourceName, modeChanges, channels=[self])
	
	def _sourceName(self, source):
		if source in self.ircd.users:
			return self.ircd.users[source].hostmask()
		if source == self.ircd.serverID:
			return self.ircd.name
		if source in self.ircd.servers:
			return self.ircd.servers[source].name
		return None
	
	def modeString(self, toUser):
		modeStr = ["+"]
		params = []
		for mode in self.modes:
			modeType = self.ircd.channelModeTypes[mode]
			if modeType not in (ModeType.ParamOnUnset, ModeType.Param, ModeType.NoParam):
				continue
			if modeType != ModeType.NoParam:
				param = self.ircd.channelModes[modeType][mode].showParam(toUser, self)
				if not param:
					param = self.modes[mode]
			else:
				param = None
			modeStr.append(mode)
			if param:
				params.append(param)
		if params:
			return "{} {}".format("".join(modeStr), " ".join(params))
		return "".join(modeStr)
	
	def userRank(self, user):
		if user not in self.users:
			return -1
		status = self.users[user]["status"]
		if not status:
			return 0
		return self.ircd.channelStatuses[status[0]][1]

class InvalidChannelName(Exception):
	def __str__(self):
		return "Invalid character in channel name"