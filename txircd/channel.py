from twisted.words.protocols import irc
from txircd.utils import CaseInsensitiveDictionary, isValidChannelName, isValidMetadataKey, ModeType, now
from weakref import WeakKeyDictionary

class IRCChannel(object):
	def __init__(self, ircd, name):
		if not isValidChannelName(name):
			raise InvalidChannelNameError
		self.ircd = ircd
		self.name = name[:self.ircd.config.get("channel_name_length", 64)]
		self.users = WeakKeyDictionary()
		self.modes = {}
		self.existedSince = now()
		self.topic = ""
		self.topicSetter = ""
		self.topicTime = now()
		self._metadata = CaseInsensitiveDictionary()
		self.cache = {}
	
	def sendUserMessage(self, command, *params, **kw):
		"""
		Sends a message to all local users in a channel.
		Accepts a command and some parameters for that command to send.
		Accepts any keyword arguments accepted by IRCUser.sendMessage.
		Also accepts the following keyword arguments:
		- skip: list of users in the channel to skip when sending the message
		"""
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
		baseTags = {}
		if "tags" in kw:
			baseTags = kw["tags"]
			del kw["tags"]
		conditionalTags = {}
		if "conditionalTags" in kw:
			conditionalTags = kw["conditionalTags"]
			del kw["conditionalTags"]
		for user in userList:
			if conditionalTags:
				tags = baseTags.copy()
				addTags = user.filterConditionalTags(conditionalTags)
				tags.update(addTags)
			else:
				tags = baseTags
			kw["tags"] = tags
			user.sendMessage(command, *params, **kw)
	
	def sendServerMessage(self, command, *params, **kw):
		"""
		Sends a message to all remote servers to which any user in this channel
		is connected. Accepts a command and some parameters for that command to
		send. Also accepts the following keyword arguments:
		- skipall: list of servers to skip from the network
		- skiplocal: list of locally-connected servers to which to skip sending
		    after we've determined the closest hop of all the servers to which
		    we're sending
		"""
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
		"""
		Sets the channel topic.
		"""
		if setter in self.ircd.users:
			source = self.ircd.users[setter].hostmask()
		elif setter == self.ircd.serverID:
			source = self.ircd.name
		elif setter in self.ircd.servers:
			source = self.ircd.servers[setter].name
		else:
			return False
		if topic == self.topic:
			return True
		oldTopic = self.topic
		self.topic = topic
		self.topicSetter = source
		self.topicTime = now()
		self.ircd.runActionStandard("topic", self, setter, oldTopic, channels=[self])
		return True
	
	def metadataKeyExists(self, key):
		"""
		Checks whether a specific key exists in the channel's metadata.
		"""
		return key in self._metadata
	
	def metadataKeyCase(self, key):
		"""
		Gets the key from the channel's metadata in its original case.
		Returns None if the key is not present.
		"""
		if key not in self._metadata:
			return None
		return self._metadata[key][0]
	
	def metadataValue(self, key):
		"""
		Gets the value for the given key in the channel's metadata.
		Returns None if the key is not present.
		"""
		if key not in self._metadata:
			return None
		return self._metadata[key][1]
	
	def metadataVisibility(self, key):
		"""
		Gets the visibility value for the given key in the channel's metadata.
		Returns None if the key is not present.
		"""
		if key not in self._metadata:
			return None
		return self._metadata[key][2]
	
	def metadataSetByUser(self, key):
		"""
		Gets whether the given metadata key/value was set by a user.
		Returns None if the key is not present.
		"""
		if key not in self._metadata:
			return None
		return self._metadata[key][3]
	
	def metadataList(self):
		"""
		Returns the list of metadata keys/values for the channel as a list of
		tuples in the format
		[ (key, value, visibility, setByUser) ]
		"""
		return self._metadata.values()
	
	def setMetadata(self, key, value, visibility, setByUser, fromServer = None):
		"""
		Sets metadata for the channel. Returns True if the set is successful or
		False if it is not. If the metadata set is caused by a message from a
		remote server, pass the server object as the fromServer parameter.
		If value is None, deletes the key provided.
		"""
		if not isValidMetadataKey(key):
			return False
		oldData = None
		if key in self._metadata:
			oldData = self._metadata[key]
		if setByUser and oldData and not oldData[3]:
			return False
		if setByUser and self.ircd.runActionUntilValue("usercansetmetadata", key, channels=[self]) is False:
			return False
		if value is None:
			del self._metadata[key]
		elif not visibility:
			return False
		else:
			self._metadata[key] = (key, value, visibility, setByUser)
		oldValue = oldData[1] if oldData else None
		self.ircd.runActionStandard("channelmetadataupdate", self, key, oldValue, value, visibility, setByUser, fromServer, channels=[self])
		return True
	
	def setModes(self, modes, defaultSource):
		"""
		Sets modes on the channel. Accepts modes as a list of tuples in the
		format:
		[ (adding, mode, param, setBy, setTime) ]
		- adding: True if we're setting the mode; False if unsetting
		- mode: The mode letter
		- param: The mode's parameter; None if no parameter is needed for that
		    mode
		- setBy: Optional, only used for list modes; a human-readable string
		    (typically server name or nick!user@host) for who/what set this
		    mode
		- setTime: Optional, only used for list modes; a datetime object
		    containing when the mode was set
		
		The defaultSource is a valid user ID or server ID of someone who set
		the modes. It is used as the source for announcements about the mode
		change and as the default setter for any list modes who do not have the
		setBy parameter specified.
		The default time for list modes with no setTime specified is now().
		"""
		modeChanges = []
		defaultSourceName = self._sourceName(defaultSource)
		if defaultSourceName is None:
			raise ValueError ("Source must be a valid user or server ID.")
		nowTime = now()
		for modeData in modes:
			mode = modeData[1]
			if mode not in self.ircd.channelModeTypes:
				continue
			setBy = defaultSourceName
			setTime = nowTime
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
				if dataCount >= 5:
					setTime = modeData[4]
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
		"""
		Parses a mode string specified by a user and sets those modes on the
		channel.
		The user parameter should be the user who set the modes.
		The modes parameter is the actual modes string; parameters specified by
		the user should be as a list of strings in params.
		The override parameter should be used only when all permission checks
		should be overridden.
		"""
		adding = True
		changes = []
		setBy = self._sourceName(user.uuid)
		setTime = now()
		for mode in modes:
			if len(changes) >= self.ircd.config.get("modes_per_line", 20):
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
				if len(changes) >= self.ircd.config.get("modes_per_line", 20):
					break
				if not override and self.ircd.runActionUntilValue("modepermission-channel-{}".format(mode), self, user, adding, parameter, users=[user], channels=[self]) is False:
					continue
				if adding:
					if modeType == ModeType.Status:
						try:
							targetUser = self.ircd.userNicks[parameter]
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
						if mode in self.modes and len(self.modes[mode]) > self.ircd.config.get("channel_listmode_limit", 128):
							user.sendMessage(irc.ERR_BANLISTFULL, self.name, parameter, "Channel +{} list is full".format(mode))
							continue
				else:
					if modeType == ModeType.Status:
						try:
							targetUser = self.ircd.userNicks[parameter]
						except KeyError:
							continue
						if mode not in self.users[targetUser]["status"]:
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
		if parameter:
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
				if mode in targetStatus:
					return False
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
					if len(self.modes[mode]) > self.ircd.config.get("channel_listmode_limit", 128):
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
			for index, paramData in enumerate(self.modes[mode]):
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
		"""
		Get a user-reportable mode string for the modes set on the channel.
		"""
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
		"""
		Gets the user's numeric rank in the channel.
		"""
		if user not in self.users:
			return -1
		status = self.users[user]["status"]
		if not status:
			return 0
		return self.ircd.channelStatuses[status[0]][1]
	
	def setCreationTime(self, time, fromServer):
		if time >= self.existedSince:
			return
		fromServerID = fromServer.serverID if fromServer else self.ircd.serverID
		self.setTopic("", fromServerID)
		
		modeResetList = []
		for mode, param in self.modes:
			modeType = self.ircd.channelModeTypes[mode]
			if modeType == ModeType.List:
				for paramValue, setBy, setTime in param:
					modeResetList.append((False, mode, paramValue, setBy, setTime))
			else:
				modeResetList.append((False, mode, param))
		for user, data in self.users.iteritems():
			if "status" not in data:
				continue
			for status in data["status"]:
				modeResetList.append((False, status, user.uuid))
		self.setModes(modeResetList, fromServerID)
		# Reset metadata
		metadataList = self.metadataList().copy()
		for key, value, visibility, setByUser in metadataList:
			self.setMetadata(key, None, visibility, False)
		
		self.existedSince = time
		self.ircd.runActionStandard("channelchangetime", self, fromServer)

class InvalidChannelNameError(Exception):
	def __str__(self):
		return "Invalid character in channel name"