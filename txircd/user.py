from twisted.internet.defer import Deferred
from twisted.words.protocols import irc
from txircd import version
from txircd.utils import ModeType, now, splitMessage
from copy import copy
from socket import gethostbyaddr, herror

irc.ERR_ALREADYREGISTERED = "462"

class IRCUser(irc.IRC):
    def __init__(self, ircd, ip):
        self.ircd = ircd
        self.uuid = ircd.createUUID()
        self.nick = None
        self.ident = None
        try:
            host = gethostbyaddr(ip)[0]
        except herror:
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
        self.ircd.users[self.uuid] = self
    
    def connectionMade(self):
        if "user_connect" in self.ircd.actions:
            for action in self.ircd.actions["user_connect"]:
                if not action[0](self):
                    self.transport.loseConnection()
                    return
    
    def dataReceived(self, data):
        data = data.replace("\r", "").replace("\n", "\r\n").replace("\0", "")
        if "user_recvdata" in self.ircd.actions:
            for action in self.ircd.actions["user_recvdata"]:
                action[0](self, data)
        irc.IRC.dataReceived(self, data)
    
    def sendLine(self, line):
        if "user_senddata" in self.ircd.actions:
            for action in self.ircd.actions["user_senddata"]:
                action[0](self, line)
        irc.IRC.sendLine(self, line)
    
    def sendMessage(self, command, *args, **kw):
        if "prefix" not in kw:
            kw["prefix"] = self.ircd.name
        if kw["prefix"] is None:
            del kw["prefix"]
        if "to" not in kw:
            kw["to"] = self.nick if self.nick else "*"
        if kw["to"] is None:
            del kw["to"]
        irc.IRC.sendMessage(self, command, *args, **kw)
    
    def handleCommand(self, command, prefix, params):
        if command in self.ircd.userCommands:
            handlers = self.ircd.userCommands[command]
            if not handlers:
                return
            data = None
            spewRegWarning = True
            for handler in handlers:
                if handler[0].forRegisteredUsers is not None:
                    if (handler[0].forRegisteredUsers is True and not self.isRegistered()) or (handler[0].forRegisteredUsers is False and self.isRegistered()):
                        continue
                spewRegWarning = False
                data = handler[0].parseParams(params)
                if data is not None:
                    break
            if data is None:
                if spewRegWarning:
                    if self.isRegistered() == 0:
                        self.sendMessage(irc.ERR_ALREADYREGISTERED, ":You may not reregister")
                    else:
                        self.sendMessage(irc.ERR_NOTREGISTERED, command, ":You have not registered")
                return
            actionName = "commandpermission-{}".format(command)
            if actionName in self.ircd.actions:
                permissionCount = 0
                for action in self.ircd.actions[actionName]:
                    result = action[0](self, command, data)
                    if result is True:
                        permissionCount += 1
                    elif result is False:
                        permissionCount -= 1
                    elif result is not None:
                        permissionCount += result
                if permissionCount < 0:
                    return
            actionName = "commandmodify-{}".format(command)
            if actionName in self.ircd.actions:
                for action in self.ircd.actions[actionName]:
                    newData = action[0](self, command, data)
                    if newData is not None:
                        data = newData
            for handler in handlers:
                if handler[0].execute(self, data):
                    if handler[0].resetsIdleTime:
                        self.idleSince = now()
                    break # If the command executor returns True, it was handled
            else:
                return # Don't process commandextra if it wasn't handled
            actionName = "commandextra-{}".format(command)
            if actionName in self.ircd.actions:
                for action in self.ircd.actions[actionName]:
                    action[0](self, command, data)
        else:
            self.sendMessage(irc.ERR_UNKNOWNCOMMAND, command, ":Unknown command")
    
    def connectionLost(self, reason):
        if self.uuid in self.ircd.users:
            self.disconnected("Connection reset")
        self.disconnectedDeferred.callback(None)
    
    def disconnected(self, reason):
        del self.ircd.users[self.uuid]
        del self.ircd.userNicks[self.nick]
        channelList = copy(self.channels)
        for channel in channelList:
            self.leave(channel)
        if "quit" in self.ircd.actions:
            for action in self.ircd.actions["quit"]:
                action[0](self, reason)
    
    def isRegistered(self):
        return not self._registerHolds
    
    def register(self, holdName):
        if holdName not in self._registerHolds:
            return
        self._registerHolds.remove(holdName)
        if not self._registerHolds:
            if self.nick in self.ircd.userNicks:
                self._registerHolds.add("NICK")
                return
            if "register" in self.ircd.actions:
                for action in self.ircd.actions["register"]:
                    if not action[0](self):
                        self.transport.loseConnection()
                        return
            self.ircd.userNicks[self.nick] = self.uuid
            self.sendMessage(irc.RPL_WELCOME, ":Welcome to the Internet Relay Chat Network {}".format(self.hostmask()))
            self.sendMessage(irc.RPL_YOURHOST, ":Your host is {}, running version {}".format(self.config["network_name"], version))
            self.sendMessage(irc.RPL_CREATED, ":This server was created {}".format(self.ircd.startupTime.replace(microsecond=0)))
            self.sendMessage(irc.RPL_MYINFO, self.config["network_name"], version, "".join(["".join(modes.keys()) for modes in self.ircd.userModes]), "".join(["".join(modes.keys()) for modes in self.ircd.channelModes]))
            isupportList = self.ircd.generateISupportList()
            isupportMsgList = splitMessage(" ".join(isupportList), 350)
            for line in isupportMsgList:
                self.sendMessage(irc.RPL_ISUPPORT, line, ":are supported by this server")
            self.handleCommand("LUSERS", None, [])
            self.handleCommand("MOTD", None, [])
            if "welcome" in self.ircd.actions:
                for action in self.ircd.actions["welcome"]:
                    action[0](self)
    
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
    
    def changeNick(self, newNick):
        if newNick in self.ircd.userNicks:
            return
        oldNick = self.nick
        del self.ircd.userNicks[self.nick]
        self.nick = newNick
        self.ircd.userNicks[self.nick] = self.uuid
        self.nickSince = now()
        if "changenick" in self.ircd.actions:
            for action in self.ircd.actions["changenick"]:
                action[0](self, oldNick)
    
    def changeIdent(self, newIdent):
        oldIdent = self.ident
        self.ident = newIdent
        if "changeident" in self.ircd.actions:
            for action in self.ircd.actions["changeident"]:
                action[0](self, oldIdent)
    
    def changeHost(self, newHost):
        oldHost = self.host
        self.host = newHost
        if "changehost" in self.ircd.actions:
            for action in self.ircd.actions["changehost"]:
                action[0](self, oldHost)
    
    def resetHost(self):
        self.changeHost(self.realhost)
    
    def changeGecos(self, newGecos):
        oldGecos = self.gecos
        self.gecos = newGecos
        if "changegecos" in self.ircd.actions:
            for action in self.ircd.actions["changegecos"]:
                action[0](self, oldGecos)
    
    def setMetadata(self, namespace, key, value):
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
        if "usermetadataupdate" in self.ircd.actions:
            for action in self.ircd.actions["usermetadataupdate"]:
                action[0](self, namespace, key, oldValue, value)
    
    def joinChannel(self, channel, override = False):
        if not override:
            if "joinpermission" in self.ircd.actions:
                permissionCount = 0
                for action in self.ircd.actions["joinpermission"]:
                    vote = action[0](channel, self)
                    if vote is True:
                        permissionCount += 1
                    elif vote is False:
                        permissionCount -= 1
                if permissionCount < 0:
                    return
        channel.users[self] = ""
        if channel.name not in self.ircd.channels:
            self.ircd.channels[channel.name] = channel
            if "channelcreate" in self.ircd.actions:
                for action in self.ircd.actions["channelcreate"]:
                    action[0](channel)
        self.channels.append(channel)
        if "joinmessage" in self.ircd.actions:
            messageUsers = channel.users.keys()
            for action in self.ircd.actions["joinmessage"]:
                actions[0](channel, self, messageUsers)
                if not messageUsers:
                    break
        if "join" in self.ircd.actions:
            for action in self.ircd.actions["join"]:
                action[0](channel, self)
    
    def leaveChannel(self, channel):
        if channel not in self.channels:
            return
        if "leave" in self.ircd.actions["leave"]:
            for action in self.ircd.actions["leave"]:
                action[0](channel, self)
        self.channels.remove(channel)
        del channel.users[self]
        if not channel.users:
            keepChannel = False
            if "channeldestroyorkeep" in self.ircd.actions:
                for action in self.ircd.actions["channeldestroyorkeep"]:
                    if action[0](channel):
                        keepChannel = True
                        break
            if not keepChannel:
                if "channeldestory" in self.ircd.actions:
                    for action in self.ircd.actions["channeldestroy"]:
                        actoin[0](channel)
                del self.ircd.channels[channel.name]
    
    def setMode(self, user, modeString, params, displaySource = None):
        adding = True
        changing = []
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
                continue
            param = None
            modeType = self.ircd.userModeTypes[mode]
            if modeType in (ModeType.List, ModeType.ParamOnUnset) or (modeType == ModeType.Param and adding):
                try:
                    param = params.pop(0)
                except IndexError:
                    continue
            paramList = [None]
            if param:
                if adding:
                    paramList = self.ircd.userModes[modeType][mode].checkSet(param)
                else:
                    paramList = self.ircd.userModes[modeType][mode].checkUnset(param)
            if paramList is None:
                continue
            del param # We use this later
            
            if user:
                displaySource = user.hostmask()
            elif not displaySource:
                displaySource = self.ircd.name
            
            for param in paramList:
                if len(changing) >= 20:
                    break
                if user and "modepermission-user-{}".format(mode) in self.ircd.actions:
                    permissionCount = 0
                    for action in self.ircd.actions["modepermission-user-{}".format(mode)]:
                        vote = action[0](self, user, mode, param)
                        if vote is True:
                            permissionCount += 1
                        else:
                            permissionCount -= 1
                    if permissionCount < 0:
                        continue
                if adding:
                    if modeType == ModeType.List:
                        if mode not in self.modes:
                            self.modes[mode] = []
                        found = False
                        for data in self.modes[mode]:
                            if data[0] == param:
                                found = True
                                break
                        if found:
                            continue
                        self.modes[mode].append((param, displaySource, now()))
                    else:
                        if mode not in self.modes or self.modes[mode] == param:
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
                changing.append((adding, mode, param, displaySource))
                if "modechange-user-{}".format(mode) in self.ircd.actions:
                    for action in self.ircd.actions["modechange-user-{}".format(mode)]:
                        action[0](self, adding, mode, param, displaySource)
        return changing