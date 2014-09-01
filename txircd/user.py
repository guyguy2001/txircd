from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import ISSLTransport
from twisted.internet.task import LoopingCall
from twisted.python import log
from twisted.words.protocols import irc
from txircd import version
from txircd.utils import ModeType, now, splitMessage
from copy import copy
from socket import gaierror, gethostbyaddr, gethostbyname, herror
from traceback import format_exc
import logging

irc.ERR_ALREADYREGISTERED = "462"

class IRCUser(irc.IRC):
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
        self.realhost = host
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
        self._registerHolds = set(("NICK", "USER"))
        self.disconnectedDeferred = Deferred()
        self._errorBatchName = None
        self._errorBatch = []
        self.ircd.users[self.uuid] = self
        self.localOnly = False
        self.secureConnection = False
        self._pinger = LoopingCall(self._ping)
        self._registrationTimeoutTimer = reactor.callLater(self.ircd.config.getWithDefault("user_registration_timeout", 10), self._timeoutRegistration)
    
    def connectionMade(self):
        if self.ircd.runActionUntilFalse("userconnect", self, users=[self]):
            self.transport.loseConnection()
            return
        if ISSLTransport.providedBy(self.transport):
            self.secureConnection = True
    
    def dataReceived(self, data):
        data = data.replace("\r", "").replace("\n", "\r\n").replace("\0", "")
        self.ircd.runActionStandard("userrecvdata", self, data, users=[self])
        try:
            irc.IRC.dataReceived(self, data)
        except Exception as ex:
            # it seems that twisted.protocols.irc makes no attempt to raise useful "invalid syntax"
            # errors. Any invalid message *should* result in a ValueError, but we can't guarentee that,
            # so let's catch everything.
            self.disconnect("Invalid data")
            log.msg("An error occurred processing data:\n{}".format(format_exc()), logLevel=logging.WARNING)
    
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
            irc.IRC.sendMessage(self, command, to, *args, **kw)
        else:
            irc.IRC.sendMessage(self, command, *args, **kw)
    
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
    
    def handleCommand(self, command, prefix, params):
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
                data = handler[0].parseParams(self, params, prefix, {})
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
            hasPermission = self.ircd.runActionUntilValue("commandpermission-{}".format(command), self, command, data, users=affectedUsers, channels=affectedChannels)
            if hasPermission is False:
                if self._hasBatchedErrors():
                    self._dispatchErrorBatch()
                return
            self._clearErrorBatch()
            if hasPermission is None: # If permission wasn't explicitly granted by a module, go through the generic commandpermission action
                hasPermission = self.ircd.runActionUntilValue("commandpermission".format(command), self, command, data, users=affectedUsers, channels=affectedChannels)
                if hasPermission is False:
                   if self._hasBatchedErrors():
                       self._dispatchErrorBatch()
                    return
            self._clearErrorBatch()
            self.ircd.runActionStandard("commandmodify-{}".format(command), self, command, data, users=affectedUsers, channels=affectedChannels) # This allows us to do processing without the "stop on empty" feature of runActionProcessing
            for handler in handlers:
                if handler[0].execute(self, data):
                    if handler[0].resetsIdleTime:
                        self.idleSince = now()
                    break # If the command executor returns True, it was handled
            else:
                return # Don't process commandextra if it wasn't handled
            self.ircd.runActionStandard("commandextra-{}".format(command), self, command, data, users=affectedUsers, channels=affectedChannels)
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
        channelList = copy(self.channels)
        for channel in channelList:
            self.leaveChannel(channel)
        self.transport.loseConnection()
    
    def _timeoutRegistration(self):
        if self.isRegistered():
            self._pinger.start(self.ircd.config.getWithDefault("user_ping_frequency", 60), False)
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
            if self.nick in self.ircd.userNicks:
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
            self.sendMessage(irc.RPL_WELCOME, ":Welcome to the Internet Relay Chat Network {}".format(self.hostmask()))
            self.sendMessage(irc.RPL_YOURHOST, ":Your host is {}, running version {}".format(self.ircd.config["network_name"], versionWithName))
            self.sendMessage(irc.RPL_CREATED, ":This server was created {}".format(self.ircd.startupTime.replace(microsecond=0)))
            chanModes = "".join(["".join(modes.keys()) for modes in self.ircd.channelModes])
            chanModes += "".join(self.ircd.channelStatuses.keys())
            self.sendMessage(irc.RPL_MYINFO, self.ircd.config["network_name"], versionWithName, "".join(["".join(modes.keys()) for modes in self.ircd.userModes]), chanModes)
            self.sendISupport()
            self.ircd.runActionStandard("welcome", self, users=[self])
    
    def sendISupport(self):
        isupportList = self.ircd.generateISupportList()
        isupportMsgList = splitMessage(" ".join(isupportList), 350)
        for line in isupportMsgList:
            self.sendMessage(irc.RPL_ISUPPORT, line, ":are supported by this server")
    
    def addRegisterHold(self, holdName):
        if not self._registerHolds:
            return
        self._registerHolds.add(holdName)
    
    def hostmask(self):
        return "{}!{}@{}".format(self.nick, self.ident, self.host)
    
    def hostmaskWithRealHost(self):
        return "{}!{}@{}".format(self.nick, self.ident, self.realhost)
    
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
    
    def changeIdent(self, newIdent):
        if newIdent == self.ident:
            return
        if len(newIdent) > 12:
            return
        oldIdent = self.ident
        self.ident = newIdent
        if self.isRegistered():
            self.ircd.runActionStandard("changeident", self, oldIdent, users=[self])
    
    def changeHost(self, newHost):
        if len(newHost) > 64:
            return
        if newHost == self.host:
            return
        oldHost = self.host
        self.host = newHost
        if self.isRegistered():
            self.ircd.runActionStandard("changehost", self, oldHost, users=[self])
    
    def resetHost(self):
        self.changeHost(self.realhost)
    
    def changeGecos(self, newGecos):
        if newGecos == self.gecos:
            return
        oldGecos = self.gecos
        self.gecos = newGecos
        if self.isRegistered():
            self.ircd.runActionStandard("changegecos", self, oldGecos, users=[self])
    
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
                if self._hasBatchedErrors():
                    self._dispatchErrorBatch()
                return
        channel.users[self] = ""
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
    
    def leaveChannel(self, channel):
        if channel not in self.channels:
            return
        self.ircd.runActionStandard("leave", channel, self, users=[self], channels=[channel])
        self.channels.remove(channel)
        del channel.users[self]
        if not channel.users:
            if not self.ircd.runActionUntilTrue("channeldestroyorkeep", channel, channels=[channel]):
                self.ircd.runActionStandard("channeldestroy", channel, channels=[channel])
                del self.ircd.channels[channel.name]
    
    def setModes(self, source, modeString, params):
        adding = True
        changing = []
        user = None
        if source in self.ircd.users:
            user = self.ircd.users[source]
            sourceName = user.hostmask()
        elif source == self.ircd.serverID:
            sourceName = self.ircd.name
        elif source in self.ircd.servers:
            sourceName = self.ircd.servers[source].name
        else:
            raise ValueError ("Source must be a valid user or server ID.")
        for mode in modeString:
            if len(changing) >= 20:
                break
            if mode == "+":
                adding = True
                continue
            if mode == "-":
                adding = False
                continue
            if mode not in self.ircd.userModeTypes:
                if user:
                    user.sendMessage(irc.ERR_UMODEUNKNOWNFLAG, mode, ":is unknown mode char to me")
                continue
            param = None
            modeType = self.ircd.userModeTypes[mode]
            if modeType in (ModeType.List, ModeType.ParamOnUnset) or (modeType == ModeType.Param and adding):
                try:
                    param = params.pop(0)
                except IndexError:
                    if modeType == ModeType.List and user:
                        self.ircd.userModes[modeType][mode].showListParams(user, self)
                    continue
            paramList = [param]
            if param:
                if adding:
                    paramList = self.ircd.userModes[modeType][mode].checkSet(self, param)
                else:
                    paramList = self.ircd.userModes[modeType][mode].checkUnset(self, param)
            if paramList is None:
                continue
            del param # We use this later
            
            for param in paramList:
                if len(changing) >= 20:
                    break
                if user and self.ircd.runActionUntilValue("modepermission-user-{}".format(mode), self, user, adding, param, users=[self, user]) is False:
                    continue
                if adding:
                    if modeType == ModeType.List:
                        if not self.addListMode(mode, param, sourceName, now(), user):
                            continue
                    else:
                        if mode in self.modes and self.modes[mode] == param:
                            continue
                        self.modes[mode] = param
                else:
                    if mode not in self.modes:
                        continue
                    if modeType == ModeType.List:
                        for index, data in enumerate(self.modes[mode]):
                            if data[0] == param:
                                del self.modes[mode][index]
                                break
                        else:
                            continue
                    else:
                        if mode in self.modes:
                            del self.modes[mode]
                        else:
                            continue
                changing.append((adding, mode, param))
                self.ircd.runActionStandard("modechange-user-{}".format(mode), self, source, adding, param, users=[self])
        if changing:
            users = []
            if user and user.uuid[:3] == self.ircd.serverID:
                users.append(user)
            if self.uuid[:3] == self.ircd.serverID:
                users.append(self)
            if users:
                self.ircd.runActionProcessing("modemessage-user", users, self, source, sourceName, changing, users=[self])
            self.ircd.runActionStandard("modechanges-user", self, source, sourceName, changing, users=[self])
        return changing
    
    def addListMode(self, mode, param, sourceName, time, settingUser = None):
        if mode not in self.modes:
            self.modes[mode] = []
        found = False
        for data in self.modes[mode]:
            if data[0] == param:
                found = True
                break
        if found:
            if not self.modes[mode]:
                del self.modes[mode]
            return False
        if len(param) > 250: # Set a max limit on param length
            if not self.modes[mode]:
                del self.modes[mode]
            return False
        if len(self.modes[mode]) > self.ircd.config.getWithDefault("user_list_limit", 100):
            if settingUser:
                settingUser.sendMessage(irc.ERR_BANLISTFULL, self.nick, param, ":User +{} list is full".format(mode))
            if not self.modes[mode]: # The config limit really shouldn't be this low, but it's possible
                del self.modes[mode]
            return False
        self.modes[mode].append((param, sourceName, time))
        return True
    
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
        to = self.nick
        if "to" in kw:
            to = kw["to"]
            del kw["to"]
        if to:
            paramList = (to,) + params
        else:
            paramList = params
        kw["users"] = [self]
        if not self.ircd.runActionUntilTrue("sendremoteusermessage-{}".format(command), self, *paramList, **kw):
            self.ircd.runActionUntilTrue("sendremoteusermessage", self, command, *paramList, **kw)
    
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
    
    def changeIdent(self, newIdent, fromRemote = False):
        if len(newIdent) > 12:
            return
        if fromRemote:
            oldIdent = self.ident
            self.ident = newIdent
            self.ircd.runActionStandard("remotechangeident", self, oldIdent, users=[self])
        else:
            self.ircd.runActionUntilTrue("remoteidentrequest", self, newIdent, users=[self])
    
    def changeHost(self, newHost, fromRemote = False):
        if len(newHost) > 64:
            return
        if fromRemote:
            oldHost = self.host
            self.host = newHost
            self.ircd.runActionStandard("remotechangehost", self, oldHost, users=[self])
        else:
            self.ircd.runActionUntilTrue("remotehostrequest", self, newHost, users=[self])
    
    def changeGecos(self, newGecos, fromRemote = False):
        if fromRemote:
            oldGecos = self.gecos
            self.gecos = newGecos
            self.ircd.runActionStandard("remotechangegecos", self, oldGecos, users=[self])
        else:
            self.ircd.runActionUntilTrue("remotegecosrequest", self, newGecos, users=[self])
    
    def joinChannel(self, channel, override = False, fromRemote = False):
        if fromRemote:
            if channel.name not in self.ircd.channels:
                self.ircd.channels[channel.name] = channel
                self.ircd.runActionStandard("channelcreate", channel, self, channels=[channel])
            channel.users[self] = ""
            self.channels.append(channel)
            messageUsers = [u for u in channel.users.iterkeys() if u.uuid[:3] == self.ircd.serverID]
            self.ircd.runActionProcessing("joinmessage", messageUsers, channel, self, users=[self], channels=[channel])
            self.ircd.runActionStandard("remotejoin", channel, self, users=[self], channels=[channel])
        else:
            self.ircd.runActionUntilTrue("remotejoinrequest", self, channel, users=[self], channels=[channel])
    
    def leaveChannel(self, channel, fromRemote = False):
        if fromRemote:
            self.ircd.runActionStandard("remoteleave", channel, self, users=[self], channels=[channel])
            self.channels.remove(channel)
            del channel.users[self]
            if not channel.users:
                if not self.ircd.runActionUntilTrue("channeldestroyorkeep", channel, channels=[channel]):
                    self.ircd.runActionStandard("channeldestroy", channel, channels=[channel])
                    del self.ircd.channels[channel.name]
        else:
            self.ircd.runActionUntilTrue("remoteleaverequest", self, channel, users=[self], channels=[channel])

class LocalUser(IRCUser):
    """
    LocalUser is a fake user created by a module, which is not
    propagated to other servers.
    """
    def __init__(self, ircd, ip, host = None):
        IRCUser.__init__(self, ircd, ip, None, host)
        self.localOnly = True
        self._sendMsgFunc = lambda self, command, *args, **kw: None
        self._registrationTimeoutTimer.cancel()
        self._registerHolds = set(("NICK",))
    
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
        self.ircd.runActionStandard("commandmodify-{}".format(command), self, command, data, users=affectedUsers, channels=affectedChannels) # This allows us to do processing without the "stop on empty" feature of runActionProcessing
        for handler in handlers:
            if handler[0].execute(self, data):
                if handler[0].resetsIdleTime:
                    self.idleSince = now()
                break
        else:
            return
        self.ircd.runActionStandard("commandextra-{}".format(command), self, command, data, users=affectedUsers, channels=affectedChannels)
    
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
        channelList = copy(self.channels)
        for channel in channelList:
            self.leaveChannel(channel)
    
    def register(self, holdName):
        if holdName not in self._registerHolds:
            return
        self._registerHolds.remove(holdName)
        if not self._registerHolds:
            self.ircd.runActionStandard("localregister", self, users=[self])
            self.ircd.userNicks[self.nick] = self.uuid
    
    def joinChannel(self, channel, override = False):
        IRCUser.joinChannel(self, channel, True)