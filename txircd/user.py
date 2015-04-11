from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import ISSLTransport
from twisted.internet.task import LoopingCall
from twisted.python import log
from twisted.words.protocols import irc
from txircd import version
from txircd.ircbase import IRCBase
from txircd.utils import ModeType, now, splitMessage
from copy import copy
from socket import gaierror, gethostbyaddr, gethostbyname, herror
from traceback import format_exc
import logging

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
				if ip == gethostbyname(resolvedHost) and len(resolvedHost) <= 64:
					host = resolvedHost
				else:
					host = ip
			except (herror, gaierror):
				host = ip
		self.host = host
		self.realHost = host
		self.ip = ip
		self.gecos = None
		self.metadata = {
			"server": {},
			"user": {},
			"client": {},
			"ext": {},
			"private": {}
		}
		self.cache = {}
		self.channels = []
		self.modes = {}
		self.connectedSince = now()
		self.nickSince = now()
		self.idleSince = now()
		self._registerHolds = set(("connection", "NICK", "USER"))
		self.disconnectedDeferred = Deferred()
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
			irc.IRC.dataReceived(self, data)
		except Exception as ex:
			# it seems that twisted.protocols.irc makes no attempt to raise useful "invalid syntax"
			# errors. Any invalid message *should* result in a ValueError, but we can't guarentee that,
			# so let's catch everything.
			log.msg("An error occurred processing data:\n{}".format(format_exc()), logLevel=logging.WARNING)
			if self.uuid in self.ircd.users:
				self.disconnect("Invalid data")
	
	def sendLine(self, line):
		self.ircd.runActionStandard("usersenddata", self, line, users=[self])
		irc.IRC.sendLine(self, line)
	
	def sendMessage(self, command, *args, **kw):
		kw["prefix"] = self._getPrefix(kw)
		if kw["prefix"] is None:
			del kw["prefix"]
		to = self.nick if self.nick else "*"
		if "to" in kw:
			to = kw["to"]
			del kw["to"]
		if to:
			IRCBase.sendMessage(self, command, to, *args, **kw)
		else:
			IRCBase.sendMessage(self, command, *args, **kw)
	
	def _getPrefix(self, msgKeywords):
		if "sourceuser" in msgKeywords:
			userTransform = IRCUser.hostmask
			if "usertransform" in msgKeywords:
				userTransform = msgKeywords["usertransform"]
			return userTransform(msgKeywords["sourceuser"])
		if "sourceserver" in msgKeywords:
			return msgKeywords["sourceserver"].name
		if "prefix" in msgKeywords:
			return msgKeywords["prefix"]
		return self.ircd.name
	
	def handleCommand(self, command, prefix, params, tags):
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
						self.sendMessage(irc.ERR_ALREADYREGISTERED, ":You may not reregister")
					else:
						self.sendMessage(irc.ERR_NOTREGISTERED, command, ":You have not registered")
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
				self.sendMessage(irc.ERR_UNKNOWNCOMMAND, command, ":Unknown command")
	
	def startErrorBatch(self, batchName):
		if not self._errorBatchName or not self._errorBatch: # Only the first batch should apply
			self._errorBatchName = batchName
		
	def sendBatchedError(self, batchName, command, *args, **kw):
		if batchName and self._errorBatchName == batchName:
			self._errorBatch.append((command, args, kw))
	
	def sendSingleError(self, batchName, command, *args, **kw):
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
	
	def connectionLost(self, reason):
		if self.uuid in self.ircd.users:
			self.disconnect("Connection reset")
		self.disconnectedDeferred.callback(None)
	
	def disconnect(self, reason):
		if self._pinger.running:
			self._pinger.stop()
		if self._registrationTimeoutTimer.active():
			self._registrationTimeoutTimer.cancel()
		del self.ircd.users[self.uuid]
		if self.isRegistered():
			del self.ircd.userNicks[self.nick]
		userSendList = [self]
		for channel in self.channels:
			userSendList.extend(channel.users.keys())
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
		return not self._registerHolds
	
	def register(self, holdName):
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
			versionWithName = "txircd-{}".format(version)
			self.sendMessage(irc.RPL_WELCOME, "Welcome to the Internet Relay Chat Network {}".format(self.hostmask()))
			self.sendMessage(irc.RPL_YOURHOST, "Your host is {}, running version {}".format(self.ircd.name, versionWithName))
			self.sendMessage(irc.RPL_CREATED, "This server was created {}".format(self.ircd.startupTime.replace(microsecond=0)))
			chanModes = "".join(["".join(modes.keys()) for modes in self.ircd.channelModes])
			chanModes += "".join(self.ircd.channelStatuses.keys())
			self.sendMessage(irc.RPL_MYINFO, self.ircd.name, versionWithName, "".join(["".join(modes.keys()) for modes in self.ircd.userModes]), chanModes)
			self.sendISupport()
			self.ircd.runActionStandard("welcome", self, users=[self])
	
	def sendISupport(self):
		isupportList = self.ircd.generateISupportList()
		isupportMsgList = splitMessage(" ".join(isupportList), 350)
		for line in isupportMsgList:
			self.sendMessage(irc.RPL_ISUPPORT, line, "are supported by this server")
	
	def addRegisterHold(self, holdName):
		if not self._registerHolds:
			return
		self._registerHolds.add(holdName)
	
	def hostmask(self):
		return "{}!{}@{}".format(self.nick, self.ident, self.host)
	
	def hostmaskWithRealHost(self):
		return "{}!{}@{}".format(self.nick, self.ident, self.realHost)
	
	def hostmaskWithIP(self):
		return "{}!{}@{}".format(self.nick, self.ident, self.ip)
	
	def changeNick(self, newNick, fromServer = None):
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
		if newIdent == self.ident:
			return
		if len(newIdent) > 12:
			return
		oldIdent = self.ident
		self.ident = newIdent
		if self.isRegistered():
			self.ircd.runActionStandard("changeident", self, oldIdent, fromServer, users=[self])
	
	def changeHost(self, newHost, fromServer = None):
		if len(newHost) > 64:
			return
		if newHost == self.host:
			return
		oldHost = self.host
		self.host = newHost
		if self.isRegistered():
			self.ircd.runActionStandard("changehost", self, oldHost, fromServer, users=[self])
	
	def resetHost(self):
		self.changeHost(self.realHost)
	
	def changeGecos(self, newGecos, fromServer = None):
		if newGecos == self.gecos:
			return
		oldGecos = self.gecos
		self.gecos = newGecos
		if self.isRegistered():
			self.ircd.runActionStandard("changegecos", self, oldGecos, fromServer, users=[self])
	
	def setMetadata(self, namespace, key, value, fromServer = None):
		if namespace not in self.metadata:
			return
		oldValue = None
		if key in self.metadata[namespace]:
			oldValue = self.metadata[namespace][key]
		if value == oldValue:
			return # Don't do any more processing, including calling the action
		if value is None:
			if key in self.metadata[namespace]:
				del self.metadata[namespace][key]
		else:
			self.metadata[namespace][key] = value
		self.ircd.runActionStandard("usermetadataupdate", self, namespace, key, oldValue, value, fromServer, users=[self])
	
	def joinChannel(self, channel, override = False):
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
		# We need to send the JOIN message before doing other processing, as chancreate will do things like
		# mode defaulting, which will send messages about the channel before the JOIN message, which is bad.
		messageUsers = [u for u in channel.users.iterkeys() if u.uuid[:3] == self.ircd.serverID]
		self.ircd.runActionProcessing("joinmessage", messageUsers, channel, self, users=messageUsers, channels=[channel])
		if newChannel:
			self.ircd.runActionStandard("channelcreate", channel, self, channels=[channel])
		self.ircd.runActionStandard("join", channel, self, users=[self], channels=[channel])
	
	def leaveChannel(self, channel, type = "PART", typeData = {}, fromServer = None):
		if channel not in self.channels:
			return
		messageUsers = [u for u in channel.users.iterkeys() if u.uuid[:3] == self.ircd.serverID]
		self.ircd.runActionProcessing("leavemessage", messageUsers, channel, self, type, typeData, fromServer, users=[self], channels=[channel])
		self.ircd.runActionStandard("leave", channel, self, users=[self], channels=[channel])
		self.channels.remove(channel)
		del channel.users[self]
	
	def setModes(self, modes, defaultSource):
		modeChanges = []
		defaultSourceName = self._sourceName(defaultSource)
		if defaultSourceName is None:
			raise ValueError ("Source must be a valid user or server ID.")
		for modeData in modes:
			mode = modeData[1]
			if mode not in self.ircd.userModeTypes:
				continue
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
				else:
					setBy = defaultSourceName
				if dataCount >= 5:
					setTime = modeData[4]
				else:
					setTime = now()
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
				if len(changing) >= 20:
					break
				if not override and self.ircd.runActionUntilValue("modepermission-user-{}".format(mode), self, user, adding, parameter, users=[self, user]) is False:
					continue
				if adding:
					if modeType == ModeType.List:
						if mode in self.modes and len(self.modes[mode]) > self.ircd.config.get("user_list_limit", 128):
							user.sendMessage(irc.ERR_BANLISTFULL, self.name, parameter, "Channel +{} list is full".format(mode))
							continue
				if self._applyMode(adding, modeType, mode, parameter, setBy, setTime):
					changes.append((adding, mode, parameter, setBy, setTime))
		self._notifyModeChanges(changes, user.uuid, setBy)
		return changes
	
	def _applyMode(self, adding, modeType, mode, parameter, setBy, setTime):
		if len(parameter) > 255:
			return False
		
		if adding:
			if modeType == ModeType.List:
				if mode in self.modes:
					if len(self.modes[mode]) > self.ircd.config.get("user_list_limit", 128):
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
		if self.uuid[:3] not in self.ircd.servers:
			raise RuntimeError ("The server for this user isn't registered in the server list!")
		kw["prefix"] = self._getPrefix(kw)
		if kw["prefix"] is None:
			del kw["prefix"]
		to = self.uuid
		if "to" in kw:
			to = kw["to"]
			del kw["to"]
		if to:
			paramList = (to,) + params
		else:
			paramList = params
		kw["users"] = [self]
		self.ircd.runComboActionUntilTrue((("sendremoteusermessage-{}".format(command), self) + paramList, ("sendremoteusermessage", self, command) + paramList), **kw)
	
	def _getPrefix(self, msgKeywords):
		if "sourceuser" in msgKeywords:
			return msgKeywords["sourceuser"].uuid
		if "sourceserver" in msgKeywords:
			return msgKeywords["sourceserver"].serverID
		if "prefix" in msgKeywords:
			return msgKeywords["prefix"]
		return self.ircd.serverID
	
	def register(self, holdName, fromRemote = False):
		if not fromRemote:
			return
		if holdName not in self._registerHolds:
			return
		self._registerHolds.remove(holdName)
		if not self._registerHolds:
			self.ircd.runActionStandard("remoteregister", self, users=[self])
			self.ircd.userNicks[self.nick] = self.uuid
	
	def addRegisterHold(self, holdName):
		pass # We're just not going to allow this here.
	
	def disconnect(self, reason, fromRemote = False):
		if fromRemote:
			if self.isRegistered():
				del self.ircd.userNicks[self.nick]
			del self.ircd.users[self.uuid]
			userSendList = []
			for channel in self.channels:
				userSendList.extend(channel.users.keys())
			userSendList = [u for u in set(userSendList) if u.uuid[:3] == self.ircd.serverID]
			channels = copy(self.channels)
			for channel in channels:
				self.leaveChannel(channel, True)
			self.ircd.runActionProcessing("quitmessage", userSendList, self, reason, users=userSendList)
			self.ircd.runActionStandard("remotequit", self, reason, users=[self])
		else:
			self.ircd.runActionUntilTrue("remotequitrequest", self, reason, users=[self])
	
	def changeNick(self, newNick, fromServer = None):
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
		if len(newIdent) > 12:
			return
		oldIdent = self.ident
		self.ident = newIdent
		if self.isRegistered():
			self.ircd.runActionStandard("remotechangeident", self, oldIdent, fromServer, users=[self])
	
	def changeHost(self, newHost, fromServer = None):
		if len(newHost) > 64:
			return
		oldHost = self.host
		self.host = newHost
		if self.isRegistered():
			self.ircd.runActionStandard("remotechangehost", self, oldHost, fromServer, users=[self])
	
	def changeGecos(self, newGecos, fromServer = None):
		oldGecos = self.gecos
		self.gecos = newGecos
		if self.isRegistered():
			self.ircd.runActionStandard("remotechangegecos", self, oldGecos, fromServer, users=[self])
	
	def joinChannel(self, channel, override = False, fromRemote = False):
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
	
	def leaveChannel(self, channel, type = "PART", typeData = {}, fromRemote = None):
		self.ircd.runActionProcessing("leavemessage", channel, self, type, typeData, fromRemote, users=[self], channels=[channel])
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
		self.ircd.runActionStandard("localregister", self, users=[self])
		self.ircd.userNicks[self.nick] = self.uuid
	
	def register(self, holdName):
		pass
	
	def setSendMsgFunc(self, func):
		self._sendMsgFunc = func
	
	def sendMessage(self, command, *args, **kw):
		self._sendMsgFunc(self, command, *args, **kw)
	
	def handleCommand(self, command, prefix, params):
		if command not in self.ircd.userCommands:
			raise ValueError ("Command not loaded")
		handlers = self.ircd.userCommands[command]
		if not handlers:
			return
		data = None
		affectedUsers = []
		affectedChannels = []
		for handler in handlers:
			if handler[0].forRegistered is False:
				continue
			data = handler[0].parseParams(self, params, prefix, {})
			if data is not None:
				affectedUsers = handler[0].affectedUsers(self, data)
				affectedChannels = handler[0].affectedChannels(self, data)
				if self not in affectedUsers:
					affectedUsers.append(self)
				break
		if data is None:
			return
		self.ircd.runComboActionStandard((("commandmodify-{}".format(command), self, data), ("commandmodify", self, command, data)), users=affectedUsers, channels=affectedChannels)
		for handler in handlers:
			if handler[0].execute(self, data):
				if handler[0].resetsIdleTime:
					self.idleSince = now()
				break
		else:
			return
		self.ircd.runComboActionStandard((("commandextra-{}".format(command), self, data), ("commandextra", self, command, data)), users=affectedUsers, channels=affectedChannels)
	
	def disconnect(self, reason):
		del self.ircd.users[self.uuid]
		del self.ircd.userNicks[self.nick]
		userSendList = [self]
		for channel in self.channels:
			userSendList.extend(channel.users.keys())
		userSendList = [u for u in set(userSendList) if u.uuid[:3] == self.ircd.serverID]
		userSendList.remove(self)
		self.ircd.runActionProcessing("quitmessage", userSendList, self, reason, users=userSendList)
		self.ircd.runActionStandard("localquit", self, reason, users=[self])
	
	def joinChannel(self, channel, override = False):
		IRCUser.joinChannel(self, channel, True)