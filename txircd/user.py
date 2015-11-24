from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import ISSLTransport
from twisted.internet.task import LoopingCall
from twisted.words.protocols import irc
from txircd import version
from txircd.ircbase import IRCBase
from txircd.utils import CaseInsensitiveDictionary, isValidHost, isValidMetadataKey, ModeType, now, splitMessage
from socket import gaierror, gethostbyaddr, gethostbyname, herror

irc.ERR_ALREADYREGISTERED = "462"

class IRCUser(IRCBase):
	def __init__(self, ircd, ip, uuid = None, host = None):
		self.ircd = ircd
		self.uuid = ircd.createUUID() if uuid is None else uuid
		self.nick = None
		self.ident = None
		if host is None:
			try:
				resolvedHost = gethostbyaddr(ip)[0]
				# First half of host resolution done, run second half to prevent rDNS spoofing.
				# Refuse hosts that are too long as well.
				if ip == gethostbyname(resolvedHost) and len(resolvedHost) <= self.ircd.config.get("hostname_length", 64) and isValidHost(resolvedHost):
					host = resolvedHost
				else:
					host = ip
			except (herror, gaierror):
				host = ip
		self.realHost = host
		self.ip = ip
		self._hostStack = []
		self._hostsByType = {}
		self.gecos = None
		self._metadata = CaseInsensitiveDictionary()
		self.cache = {}
		self.channels = []
		self.modes = {}
		self.connectedSince = now()
		self.nickSince = now()
		self.idleSince = now()
		self._registerHolds = set(("connection", "NICK", "USER"))
		self.disconnectedDeferred = Deferred()
		self._messageBatches = {}
		self._errorBatchName = None
		self._errorBatch = []
		self.ircd.users[self.uuid] = self
		self.localOnly = False
		self.secureConnection = False
		self._pinger = LoopingCall(self._ping)
		self._registrationTimeoutTimer = reactor.callLater(self.ircd.config.get("user_registration_timeout", 10), self._timeoutRegistration)
	
	def connectionMade(self):
		# We need to callLater the connect action call because the connection isn't fully set up yet,
		# nor is it fully set up even with a delay of zero, which causes the message buffer not to be sent
		# when the connection is closed.
		# The "connection" register hold is used basically solely for the purposes of this to prevent potential
		# race conditions with registration.
		reactor.callLater(0.1, self._callConnectAction)
		if ISSLTransport.providedBy(self.transport):
			self.secureConnection = True
	
	def _callConnectAction(self):
		if self.ircd.runActionUntilFalse("userconnect", self, users=[self]):
			self.transport.loseConnection()
		else:
			self.register("connection")
	
	def dataReceived(self, data):
		self.ircd.runActionStandard("userrecvdata", self, data, users=[self])
		try:
			IRCBase.dataReceived(self, data)
		except Exception:
			self.ircd.log.failure("An error occurred while processing incoming data.")
			if self.uuid in self.ircd.users:
				self.disconnect("Error occurred")
	
	def sendLine(self, line):
		self.ircd.runActionStandard("usersenddata", self, line, users=[self])
		IRCBase.sendLine(self, line)
	
	def sendMessage(self, command, *args, **kw):
		"""
		Sends the given message to this user.
		Accepts the following keyword arguments:
		- prefix: The message prefix or None to suppress the default prefix
		    If not given, defaults to the server name.
		- to: The destination of the message or None if the message has no
		    destination. The implicit destination is this user if this
		    argument isn't specified.
		- tags: Dict of message tags to send.
		"""
		if "prefix" not in kw:
			kw["prefix"] = self.ircd.name
		if kw["prefix"] is None:
			del kw["prefix"]
		to = self.nick if self.nick else "*"
		if "to" in kw:
			to = kw["to"]
			del kw["to"]
		if to:
			args = [to] + list(args)
		self.ircd.runActionStandard("modifyoutgoingmessage", self, command, args, kw)
		IRCBase.sendMessage(self, command, *args, **kw)
	
	def handleCommand(self, command, params, prefix, tags):
		if self.uuid not in self.ircd.users:
			return # we have been disconnected - ignore all further commands
		if command in self.ircd.userCommands:
			handlers = self.ircd.userCommands[command]
			if not handlers:
				return
			data = None
			spewRegWarning = True
			affectedUsers = []
			affectedChannels = []
			for handler in handlers:
				if handler[0].forRegistered is not None:
					if (handler[0].forRegistered is True and not self.isRegistered()) or (handler[0].forRegistered is False and self.isRegistered()):
						continue
				spewRegWarning = False
				data = handler[0].parseParams(self, params, prefix, tags)
				if data is not None:
					affectedUsers = handler[0].affectedUsers(self, data)
					affectedChannels = handler[0].affectedChannels(self, data)
					if self not in affectedUsers:
						affectedUsers.append(self)
					break
			if data is None:
				if spewRegWarning:
					if self.isRegistered() == 0:
						self.sendMessage(irc.ERR_ALREADYREGISTERED, "You may not reregister")
					else:
						self.sendMessage(irc.ERR_NOTREGISTERED, command, "You have not registered")
				elif self._hasBatchedErrors():
					self._dispatchErrorBatch()
				return
			self._clearErrorBatch()
			if self.ircd.runComboActionUntilValue((("commandpermission-{}".format(command), self, data), ("commandpermission", self, command, data)), users=affectedUsers, channels=affectedChannels) is False:
				return
			self.ircd.runComboActionStandard((("commandmodify-{}".format(command), self, data), ("commandmodify", self, command, data)), users=affectedUsers, channels=affectedChannels) # This allows us to do processing without the "stop on empty" feature of runActionProcessing
			for handler in handlers:
				if handler[0].execute(self, data):
					if handler[0].resetsIdleTime:
						self.idleSince = now()
					break # If the command executor returns True, it was handled
			else:
				return # Don't process commandextra if it wasn't handled
			self.ircd.runComboActionStandard((("commandextra-{}".format(command), self, data), ("commandextra", self, command, data)), users=affectedUsers, channels=affectedChannels)
		else:
			if not self.ircd.runActionFlagTrue("commandunknown", self, command, params, {}):
				self.sendMessage(irc.ERR_UNKNOWNCOMMAND, command, "Unknown command")
	
	def createMessageBatch(self, batchName, batchType, batchParameters = None):
		"""
		Start a new message batch with the given batch name, type, and list of parameters.
		If a batch with the given name already exists, that batch will be overwritten.
		"""
		self._messageBatches[batchName] = { "type": batchType, "parameters": batchParameters, "messages": [] }
	
	def sendMessageInBatch(self, batchName, command, *args, **kw):
		"""
		Adds a message to the batch with the given name.
		"""
		if batchName not in self._messageBatches:
			return
		self._messageBatches[batchName]["messages"].append((command, args, kw))
	
	def sendBatch(self, batchName):
		"""
		Sends the messages in the given batch to the user.
		"""
		if batchName not in self._messageBatches:
			return
		batchType = self._messageBatches[batchName]["type"]
		batchParameters = self._messageBatches[batchName]["parameters"]
		self.ircd.runActionStandard("startbatchsend", self, batchName, batchType, batchParameters)
		for messageData in self._messageBatches[batchName]["messages"]:
			self.sendMessage(messageData[0], *messageData[1], **messageData[2])
		self.ircd.runActionStandard("endbatchsend", self, batchName, batchType, batchParameters)
	
	def startErrorBatch(self, batchName):
		"""
		Used to start an error batch when sending multiple error messages to a
		user from a command's parseParams or from the commandpermission action.
		"""
		if not self._errorBatchName or not self._errorBatch: # Only the first batch should apply
			self._errorBatchName = batchName
		
	def sendBatchedError(self, batchName, command, *args, **kw):
		"""
		Adds an error to the current error batch if the specified error batch
		is the current error batch.
		"""
		if batchName and self._errorBatchName == batchName:
			self._errorBatch.append((command, args, kw))
	
	def sendSingleError(self, batchName, command, *args, **kw):
		"""
		Creates a batch containing a single error and adds the specified error
		to it.
		"""
		if not self._errorBatchName:
			self._errorBatchName = batchName
			self._errorBatch.append((command, args, kw))
	
	def _hasBatchedErrors(self):
		if self._errorBatch:
			return True
		return False
	
	def _clearErrorBatch(self):
		self._errorBatchName = None
		self._errorBatch = []
	
	def _dispatchErrorBatch(self):
		for error in self._errorBatch:
			self.sendMessage(error[0], *error[1], **error[2])
		self._clearErrorBatch()
	
	def filterConditionalTags(self, conditionalTags):
		applyTags = {}
		for tag, data in conditionalTags.iteritems():
			value, check = data
			if check(self):
				applyTags[tag] = value
		return applyTags
	
	def connectionLost(self, reason):
		if self.uuid in self.ircd.users:
			self.disconnect("Connection reset")
		self.disconnectedDeferred.callback(None)
	
	def disconnect(self, reason):
		"""
		Disconnects the user from the server.
		"""
		self.ircd.log.debug("Disconnecting user {user.uuid} ({user.hostmask()}): {reason}", user=self, reason=reason)
		if self._pinger:
			if self._pinger.running:
				self._pinger.stop()
			self._pinger = None
		if self._registrationTimeoutTimer:
			if self._registrationTimeoutTimer.active():
				self._registrationTimeoutTimer.cancel()
			self._registrationTimeoutTimer = None
		self.ircd.recentlyQuitUsers[self.uuid] = now()
		del self.ircd.users[self.uuid]
		if self.isRegistered():
			del self.ircd.userNicks[self.nick]
		userSendList = [self]
		while self.channels:
			channel = self.channels[0]
			userSendList.extend(channel.users.keys())
			self._leaveChannel(channel)
		userSendList = [u for u in set(userSendList) if u.uuid[:3] == self.ircd.serverID]
		userSendList.remove(self)
		self.ircd.runActionProcessing("quitmessage", userSendList, self, reason, users=[self] + userSendList)
		self.ircd.runActionStandard("quit", self, reason, users=self)
		self.transport.loseConnection()
	
	def _timeoutRegistration(self):
		if self.isRegistered():
			self._pinger.start(self.ircd.config.get("user_ping_frequency", 60), False)
			return
		self.disconnect("Registration timeout")
	
	def _ping(self):
		self.ircd.runActionStandard("pinguser", self)
	
	def isRegistered(self):
		"""
		Returns True if this user session is fully registered.
		"""
		return not self._registerHolds
	
	def register(self, holdName):
		"""
		Removes the specified hold on a user's registratrion. If this is the
		last hold on a user, completes registration on the user.
		"""
		if holdName not in self._registerHolds:
			return
		self._registerHolds.remove(holdName)
		if not self._registerHolds:
			if not self.nick or self.nick in self.ircd.userNicks:
				self._registerHolds.add("NICK")
			if not self.ident or not self.gecos:
				self._registerHolds.add("USER")
			if self._registerHolds:
				return
			self.ircd.userNicks[self.nick] = self.uuid
			if self.ircd.runActionUntilFalse("register", self, users=[self]):
				self.transport.loseConnection()
				return
			self.ircd.log.debug("Registering user {user.uuid} ({user.hostmask()})", user=self)
			versionWithName = "txircd-{}".format(version)
			self.sendMessage(irc.RPL_WELCOME, "Welcome to the Internet Relay Chat Network {}".format(self.hostmask()))
			self.sendMessage(irc.RPL_YOURHOST, "Your host is {}, running version {}".format(self.ircd.name, versionWithName))
			self.sendMessage(irc.RPL_CREATED, "This server was created {}".format(self.ircd.startupTime.replace(microsecond=0)))
			chanModes = "".join(["".join(modes.keys()) for modes in self.ircd.channelModes])
			chanModes += "".join(self.ircd.channelStatuses.keys())
			self.sendMessage(irc.RPL_MYINFO, self.ircd.name, versionWithName, "".join(["".join(modes.keys()) for modes in self.ircd.userModes]), chanModes)
			self.sendISupport()
			self.ircd.runActionStandard("welcome", self, users=[self])
	
	def addRegisterHold(self, holdName):
		"""
		Adds a register hold to this user if the user is not yet registered.
		"""
		if not self._registerHolds:
			return
		self._registerHolds.add(holdName)
	
	def sendISupport(self):
		"""
		Sends ISUPPORT to this user."""
		isupportList = self.ircd.generateISupportList()
		isupportMsgList = splitMessage(" ".join(isupportList), 350)
		for line in isupportMsgList:
			lineArgs = line.split(" ")
			lineArgs.append("are supported by this server")
			self.sendMessage(irc.RPL_ISUPPORT, *lineArgs)
	
	def hostmask(self):
		"""
		Returns the user's hostmask.
		"""
		return "{}!{}@{}".format(self.nick, self.ident, self.host())
	
	def hostmaskWithRealHost(self):
		"""
		Returns the user's hostmask using the user's real host rather than any
		vhost that may have been applied.
		"""
		return "{}!{}@{}".format(self.nick, self.ident, self.realHost)
	
	def hostmaskWithIP(self):
		"""
		Returns the user's hostmask using the user's IP address instead of the
		host.
		"""
		return "{}!{}@{}".format(self.nick, self.ident, self.ip)
	
	def changeNick(self, newNick, fromServer = None):
		"""
		Changes this user's nickname. If initiated by a remote server, that
		server should be specified in the fromServer parameter.
		"""
		if newNick == self.nick:
			return
		if newNick in self.ircd.userNicks and self.ircd.userNicks[newNick] != self.uuid:
			return
		oldNick = self.nick
		if oldNick and oldNick in self.ircd.userNicks:
			del self.ircd.userNicks[self.nick]
		self.nick = newNick
		self.nickSince = now()
		if self.isRegistered():
			self.ircd.userNicks[self.nick] = self.uuid
			userSendList = [self]
			for channel in self.channels:
				userSendList.extend(channel.users.keys())
			userSendList = [u for u in set(userSendList) if u.uuid[:3] == self.ircd.serverID]
			self.ircd.runActionProcessing("changenickmessage", userSendList, self, oldNick, users=userSendList)
			self.ircd.runActionStandard("changenick", self, oldNick, fromServer, users=[self])
	
	def changeIdent(self, newIdent, fromServer = None):
		"""
		Changes this user's ident. If initiated by a remote server, that server
		should be specified in the fromServer parameter.
		"""
		if newIdent == self.ident:
			return
		if len(newIdent) > self.ircd.config.get("ident_length", 12):
			return
		oldIdent = self.ident
		self.ident = newIdent
		if self.isRegistered():
			self.ircd.runActionStandard("changeident", self, oldIdent, fromServer, users=[self])
	
	def host(self):
		if not self._hostStack:
			return self.realHost
		return self._hostsByType[self._hostStack[-1]]
	
	def changeHost(self, hostType, newHost, fromServer = None):
		"""
		Changes a user's host. If initiated by a remote server, that server
		should be specified in the fromServer parameter.
		"""
		if hostType == "*":
			return
		if len(newHost) > self.ircd.config.get("hostname_length", 64):
			return
		if hostType in self._hostsByType and self._hostsByType[hostType] == newHost:
			return
		oldHost = self.host()
		self._hostsByType[hostType] = newHost
		if hostType in self._hostStack:
			self._hostStack.remove(hostType)
		self._hostStack.append(hostType)
		if self.isRegistered():
			self.ircd.runComboActionStandard((("changehost", self, hostType, oldHost, fromServer), ("updatehost", self, hostType, oldHost, newHost, fromServer)), users=[self])
	
	def updateHost(self, hostType, newHost, fromServer = None):
		"""
		Updates the host of a given host type for the user. If initiated by
		a remote server, that server should be specified in the fromServer
		parameter.
		"""
		if hostType not in self._hostStack:
			self.changeHost(hostType, newHost, fromServer)
			return
		if hostType == "*":
			return
		if len(newHost) > self.ircd.config.get("hostname_length", 64):
			return
		if hostType in self._hostsByType and self._hostsByType[hostType] == newHost:
			return
		oldHost = self.host()
		oldHostOfType = None
		if hostType in self._hostsByType:
			oldHostOfType = self._hostsByType[hostType]
		self._hostsByType[hostType] = newHost
		changedUserHost = (oldHost != self.host())
		changedHostOfType = (oldHostOfType != newHost)
		if self.isRegistered():
			if changedUserHost and changedHostOfType:
				self.ircd.runComboActionStandard((("changehost", self, hostType, oldHost, fromServer), ("updatehost", self, hostType, oldHost, newHost, fromServer)), users=[self])
			elif changedHostOfType:
				self.ircd.runActionStandard("updatehost", self, hostType, oldHost, newHost, fromServer, users=[self])
	
	def resetHost(self, hostType, fromServer):
		"""
		Resets the user's host to the real host.
		"""
		if hostType not in self._hostsByType:
			return
		oldHost = self.host()
		if hostType in self._hostStack:
			self._hostStack.remove(hostType)
		del self._hostsByType[hostType]
		currentHost = self.host()
		if currentHost != oldHost:
			self.ircd.runComboActionStandard((("changehost", self, hostType, oldHost, fromServer), ("updatehost", self, hostType, oldHost, None, fromServer)), users=[self])
		else:
			self.ircd.runActionStandard("updatehost", self, hostType, oldHost, None, fromServer, users=[self])
	
	def currentHostType(self):
		if self._hostStack:
			return self._hostStack[-1]
		return "*"
	
	def changeGecos(self, newGecos, fromServer = None):
		"""
		Changes a user's real name. If initiated by a remote server, that
		server should be specified in the fromServer parameter.
		"""
		if len(newGecos) > self.ircd.config.get("gecos_length", 128):
			return
		if newGecos == self.gecos:
			return
		oldGecos = self.gecos
		self.gecos = newGecos
		if self.isRegistered():
			self.ircd.runActionStandard("changegecos", self, oldGecos, fromServer, users=[self])
	
	def metadataKeyExists(self, key):
		"""
		Checks whether the specified key exists in the user's metadata.
		"""
		return key in self._metadata
	
	def metadataKeyCase(self, key):
		"""
		Returns the specified key in the user's metadata in its original case.
		Returns None if the given key is not in the user's metadata.
		"""
		if key not in self._metadata:
			return None
		return self.metadata[key][0]
	
	def metadataValue(self, key):
		"""
		Returns the value of the given key in the user's metadata or None if
		the given key is not in the user's metadata.
		"""
		if key not in self._metadata:
			return None
		return self._metadata[key][1]
	
	def metadataVisibility(self, key):
		"""
		Returns the visibility value of the given key in the user's metadata or
		None if the given key is not in the user's metadata.
		"""
		if key not in self._metadata:
			return None
		return self._metadata[key][2]
	
	def metadataSetByUser(self, key):
		"""
		Returns whether the given key in the user's metadata was set by a user
		or None if the given key is not in the user's metadata.
		"""
		if key not in self._metadata:
			return None
		return self._metadata[key][3]
	
	def metadataList(self):
		"""
		Returns the list of metadata keys/values for the user as a list of
		tuples in the format
		[ (key, value, visibility, setByUser) ]
		"""
		return self._metadata.values()
	
	def setMetadata(self, key, value, visibility, setByUser, fromServer = None):
		"""
		Sets metadata for the user. If initiated by a remote server, that
		server should be specified in the fromServer parameter.
		If the value is None, deletes the metadata at the provided key.
		"""
		if not isValidMetadataKey(key):
			return False
		oldData = None
		if key in self._metadata:
			oldData = self._metadata[key]
		if setByUser and oldData and not oldData[3]:
			return False
		if setByUser and self.ircd.runActionUntilValue("usercansetmetadata", key, users=[self]) is False:
			return False
		if value is None:
			if key in self._metadata:
				del self._metadata[key]
		elif not visibility:
			return False
		else:
			self._metadata[key] = (key, value, visibility, setByUser)
		oldValue = oldData[1] if oldData else None
		self.ircd.runActionStandard("usermetadataupdate", self, key, oldValue, value, visibility, setByUser, fromServer, users=[self])
		return True
	
	def joinChannel(self, channel, override = False):
		"""
		Joins the user to a channel. Specify the override parameter only if all
		permission checks should be bypassed.
		"""
		if channel in self.channels:
			return
		if not override:
			if self.ircd.runActionUntilValue("joinpermission", channel, self, users=[self], channels=[channel]) is False:
				return
		channel.users[self] = { "status": "" }
		self.channels.append(channel)
		newChannel = False
		if channel.name not in self.ircd.channels:
			newChannel = True
			self.ircd.channels[channel.name] = channel
			self.ircd.recentlyDestroyedChannels[channel.name] = False
		# We need to send the JOIN message before doing other processing, as chancreate will do things like
		# mode defaulting, which will send messages about the channel before the JOIN message, which is bad.
		messageUsers = [u for u in channel.users.iterkeys() if u.uuid[:3] == self.ircd.serverID]
		self.ircd.runActionProcessing("joinmessage", messageUsers, channel, self, users=messageUsers, channels=[channel])
		if newChannel:
			self.ircd.runActionStandard("channelcreate", channel, self, channels=[channel])
		self.ircd.runActionStandard("join", channel, self, users=[self], channels=[channel])
	
	def leaveChannel(self, channel, partType = "PART", typeData = {}, fromServer = None):
		"""
		Removes the user from a channel. The partType and typeData are used for
		the leavemessage action to send the parting message. If the channel
		leaving is initiated by a remote server, that server should be
		specified in the fromServer parameter.
		"""
		if channel not in self.channels:
			return
		messageUsers = [u for u in channel.users.iterkeys() if u.uuid[:3] == self.ircd.serverID]
		self.ircd.runActionProcessing("leavemessage", messageUsers, channel, self, partType, typeData, fromServer, users=[self], channels=[channel])
		self._leaveChannel(channel)
	
	def _leaveChannel(self, channel):
		self.ircd.runActionStandard("leave", channel, self, users=[self], channels=[channel])
		self.channels.remove(channel)
		del channel.users[self]
	
	def setModes(self, modes, defaultSource):
		"""
		Sets modes on the user. Accepts modes as a list of tuples in the
		format:
		[ (adding, mode, param, setBy, setTime) ]
		- adding: True if we're setting the mode; False if unsetting
		- mode: The mode letter
		- param: The mode's parameter; None if no parameter is needed for that
		    mode
		- setBy: Optional, only used for list modes; a human-readable string
		    (typically server name or nick!user@host) for who/what set this
		    mode)
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
			if mode not in self.ircd.userModeTypes:
				continue
			setBy = defaultSourceName
			setTime = nowTime
			modeType = self.ircd.userModeTypes[mode]
			adding = modeData[0]
			if modeType in (ModeType.List, ModeType.ParamOnUnset, ModeType.Param):
				param = modeData[2]
			else:
				param = None
			if modeType == ModeType.List:
				dataCount = len(modeData)
				if dataCount >= 4:
					setBy = modeData[3]
				if dataCount >= 5:
					setTime = modeData[4]
			if adding:
				paramList = self.ircd.userModes[modeType][mode].checkSet(self, param)
			else:
				paramList = self.ircd.userModes[modeType][mode].checkUnset(self, param)
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
		user.
		The user parameter should be the user who set the modes (usually, but
		not always, this user).
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
			if mode not in self.ircd.userModeTypes:
				user.sendMessage(irc.ERR_UNKNOWNMODE, mode, "is unknown mode char to me")
				continue
			modeType = self.ircd.userModeTypes[mode]
			param = None
			if modeType in (ModeType.List, ModeType.ParamOnUnset) or (adding and modeType == ModeType.Param):
				try:
					param = params.pop(0)
				except IndexError:
					if modeType == ModeType.List:
						self.ircd.userModes[modeType][mode].showListParams(user, self)
					continue
			if adding:
				paramList = self.ircd.userModes[modeType][mode].checkSet(self, param)
			else:
				paramList = self.ircd.userModes[modeType][mode].checkUnset(self, param)
			if paramList is None:
				continue
			
			for parameter in paramList:
				if len(changes) >= self.ircd.config.get("modes_per_line", 20):
					break
				if not override and self.ircd.runActionUntilValue("modepermission-user-{}".format(mode), self, user, adding, parameter, users=[self, user]) is False:
					continue
				if adding:
					if modeType == ModeType.List:
						if mode in self.modes and len(self.modes[mode]) > self.ircd.config.get("user_listmode_limit", 128):
							user.sendMessage(irc.ERR_BANLISTFULL, self.name, parameter, "Channel +{} list is full".format(mode))
							continue
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
			if modeType == ModeType.List:
				if mode in self.modes:
					if len(self.modes[mode]) > self.ircd.config.get("user_listmode_limit", 128):
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
		for change in modeChanges:
			self.ircd.runActionStandard("modechange-user-{}".format(change[1]), self, change[3], change[0], change[2], users=[self])
		
		users = []
		if source in self.ircd.users and source[:3] == self.ircd.serverID:
			users.append(self.ircd.users[source])
		if self.uuid[:3] == self.ircd.serverID:
			users.append(self)
		if users:
			self.ircd.runActionProcessing("modemessage-user", users, self, source, sourceName, modeChanges, users=users)
		self.ircd.runActionStandard("modechanges-user", self, source, sourceName, modeChanges, users=[self])
	
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
		Get a user-reportable mode string for the modes set on the user.
		"""
		modeStr = ["+"]
		params = []
		for mode in self.modes:
			modeType = self.ircd.userModeTypes[mode]
			if modeType not in (ModeType.ParamOnUnset, ModeType.Param, ModeType.NoParam):
				continue
			if modeType != ModeType.NoParam:
				param = None
				if toUser:
					param = self.ircd.userModes[modeType][mode].showParam(toUser, self)
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

class RemoteUser(IRCUser):
	def __init__(self, ircd, ip, uuid = None, host = None):
		IRCUser.__init__(self, ircd, ip, uuid, host)
		self._registrationTimeoutTimer.cancel()
	
	def sendMessage(self, command, *params, **kw):
		pass # Messages can't be sent directly to remote users.
	
	def register(self, holdName, fromRemote = False):
		"""
		Handles registration of a remote user.
		"""
		if not fromRemote:
			return
		if holdName not in self._registerHolds:
			return
		self.ircd.log.debug("Registered remote user {user.uuid} ({user.hostmask()})", user=self)
		self._registerHolds.remove(holdName)
		if not self._registerHolds:
			self.ircd.runActionStandard("remoteregister", self, users=[self])
			self.ircd.userNicks[self.nick] = self.uuid
	
	def addRegisterHold(self, holdName):
		pass # We're just not going to allow this here.
	
	def disconnect(self, reason, fromRemote = False):
		"""
		Disconnects the remote user from the remote server.
		"""
		if fromRemote:
			if self.isRegistered():
				del self.ircd.userNicks[self.nick]
			self.ircd.recentlyQuitUsers[self.uuid] = now()
			del self.ircd.users[self.uuid]
			userSendList = []
			while self.channels:
				channel = self.channels[0]
				userSendList.extend(channel.users.keys())
				self._leaveChannel(channel)
			userSendList = [u for u in set(userSendList) if u.uuid[:3] == self.ircd.serverID]
			self.ircd.runActionProcessing("quitmessage", userSendList, self, reason, users=userSendList)
			self.ircd.runActionStandard("remotequit", self, reason, users=[self])
		else:
			self.ircd.runActionUntilTrue("remotequitrequest", self, reason, users=[self])
	
	def changeNick(self, newNick, fromServer = None):
		"""
		Changes the nickname of the user. If the change was initiated by a
		remote server, that server should be specified as the fromServer
		parameter.
		"""
		oldNick = self.nick
		if self.nick and self.nick in self.ircd.userNicks and self.ircd.userNicks[self.nick] == self.uuid:
			del self.ircd.userNicks[self.nick]
		self.nick = newNick
		self.ircd.userNicks[self.nick] = self.uuid
		if self.isRegistered():
			userSendList = [self]
			for channel in self.channels:
				userSendList.extend(channel.users.keys())
			userSendList = [u for u in set(userSendList) if u.uuid[:3] == self.ircd.serverID]
			self.ircd.runActionProcessing("changenickmessage", userSendList, self, oldNick, users=userSendList)
			self.ircd.runActionStandard("remotechangenick", self, oldNick, fromServer, users=[self])
	
	def changeIdent(self, newIdent, fromServer = None):
		"""
		Changes the ident of the user. If the change was initiated by a remote
		server, that server should be specified as the fromServer parameter.
		"""
		if len(newIdent) > self.ircd.config.get("ident_length", 12):
			return
		oldIdent = self.ident
		self.ident = newIdent
		if self.isRegistered():
			self.ircd.runActionStandard("remotechangeident", self, oldIdent, fromServer, users=[self])
	
	def changeGecos(self, newGecos, fromServer = None):
		"""
		Changes the real name of the user. If the change was initiated by a
		remote server, that server should be specified as the fromServer
		parameter.
		"""
		oldGecos = self.gecos
		self.gecos = newGecos
		if self.isRegistered():
			self.ircd.runActionStandard("remotechangegecos", self, oldGecos, fromServer, users=[self])
	
	def joinChannel(self, channel, override = False, fromRemote = False):
		"""
		Joins the user to a channel.
		"""
		if fromRemote:
			if channel in self.channels:
				return
			newChannel = False
			if channel.name not in self.ircd.channels:
				newChannel = True
				self.ircd.channels[channel.name] = channel
			channel.users[self] = { "status": "" }
			self.channels.append(channel)
			messageUsers = [u for u in channel.users.iterkeys() if u.uuid[:3] == self.ircd.serverID]
			self.ircd.runActionProcessing("joinmessage", messageUsers, channel, self, users=[self], channels=[channel])
			if newChannel:
				self.ircd.runActionStandard("channelcreate", channel, self, channels=[channel])
			self.ircd.runActionStandard("remotejoin", channel, self, users=[self], channels=[channel])
		else:
			self.ircd.runActionUntilTrue("remotejoinrequest", self, channel, users=[self], channels=[channel])
	
	def _leaveChannel(self, channel):
		self.ircd.runActionStandard("remoteleave", channel, self, users=[self], channels=[channel])
		self.channels.remove(channel)
		del channel.users[self]

class LocalUser(IRCUser):
	"""
	LocalUser is a fake user created by a module, which is not
	propagated to other servers.
	"""
	def __init__(self, ircd, nick, ident, host, ip, gecos):
		IRCUser.__init__(self, ircd, ip, None, host)
		self.localOnly = True
		self._sendMsgFunc = lambda self, command, *args, **kw: None
		self._registrationTimeoutTimer.cancel()
		del self._registerHolds
		self._pinger = None
		self.nick = nick
		self.ident = ident
		self.gecos = gecos
		self.ircd.log.debug("Created new local user {user.uuid} ({user.hostmask()})", user=self)
		self.ircd.runActionStandard("localregister", self, users=[self])
		self.ircd.userNicks[self.nick] = self.uuid
	
	def register(self, holdName):
		pass
	
	def setSendMsgFunc(self, func):
		"""
		Sets the function to call when a message is sent to this user.
		"""
		self._sendMsgFunc = func
	
	def sendMessage(self, command, *args, **kw):
		"""
		Sends a message to this user.
		"""
		self._sendMsgFunc(self, command, *args, **kw)
	
	def disconnect(self, reason):
		"""
		Cleans up and removes the user.
		"""
		del self.ircd.users[self.uuid]
		del self.ircd.userNicks[self.nick]
		userSendList = [self]
		for channel in self.channels:
			userSendList.extend(channel.users.keys())
		userSendList = [u for u in set(userSendList) if u.uuid[:3] == self.ircd.serverID]
		userSendList.remove(self)
		self.ircd.log.debug("Removing local user {user.uuid} ({user.hostmask()}): {reason}", user=self, reason=reason)
		self.ircd.runActionProcessing("quitmessage", userSendList, self, reason, users=userSendList)
		self.ircd.runActionStandard("localquit", self, reason, users=[self])
	
	def joinChannel(self, channel, override = False):
		"""
		Joins the user to a channel.
		"""
		IRCUser.joinChannel(self, channel, True)