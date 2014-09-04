from twisted.plugin import IPlugin
from twisted.python import log
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType, timestamp
from zope.interface import implements
import logging

irc.RPL_CREATIONTIME = "329"

class ModeCommand(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "ModeCommand"
    core = True
    minLevel = 100
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("modemessage-channel", 1, self.sendChannelModesToUsers),
                ("modechanges-channel", 1, self.sendChannelModesToServers),
                ("modemessage-user", 1, self.sendUserModesToUsers),
                ("modechanges-user", 1, self.sendUserModesToServers),
                ("commandpermission-MODE", 1, self.restrictUse) ]
    
    def userCommands(self):
        return [ ("MODE", 1, UserMode(self.ircd)) ]
    
    def serverCommands(self):
        return [ ("MODE", 1, ServerMode(self.ircd)) ]
    
    def load(self):
        self.rehash()
    
    def rehash(self):
        newLevel = self.ircd.config.getWithDefault("channel_minimum_level_mode", 100)
        try:
            self.minLevel = int(newLevel)
        except ValueError:
            try:
                self.minLevel = self.ircd.channelStatuses[newLevel[0]][1]
            except KeyError:
                log.msg("ModeCommand: No valid minimum level found; defaulting to 100", logLevel=logging.WARNING)
                self.minLevel = 100
    
    def getOutputModes(self, modes):
        addInStr = None
        modeStrList = []
        params = []
        modeLists = []
        modeLen = 0
        for modeData in modes:
            adding, mode, param = modeData
            paramLen = 0
            if param is not None:
                paramLen = len(param)
            if modeLen + paramLen + 3 > 300: # Don't let the mode output get too long
                modeLists.append(["".join(modeStrList)] + params)
                addInStr = None
                modeStrList = []
                params = []
                modeLen = 0
            if adding != addInStr:
                if adding:
                    modeStrList.append("+")
                else:
                    modeStrList.append("-")
                addInStr = adding
                modeLen += 1
            modeStrList.append(mode)
            modeLen += 1
            if param is not None:
                params.append(param)
                modeLen += 1 + paramLen
        modeLists.append(["".join(modeStrList)] + params)
        return modeLists
    
    def sendChannelModesToUsers(self, users, channel, source, sourceName, modes):
        modeOuts = self.getOutputModes(modes)
        for modeOut in modeOuts:
            modeStr = modeOut[0]
            params = modeOut[1:]
            for user in users:
                user.sendMessage("MODE", modeStr, *params, prefix=sourceName, to=channel.name)
        del users[:]
    
    def sendChannelModesToServers(self, channel, source, sourceName, modes):
        modeOuts = self.getOutputModes(modes)
        
        if source[:3] == self.ircd.serverID:
            fromServer = None
        else:
            fromServer = self.ircd.servers[source[:3]]
            while fromServer.nextClosest != self.ircd.serverID:
                fromServer = self.ircd.servers[fromServer.nextClosest]
        for modeOut in modeOuts:
            modeStr = modeOut[0]
            params = modeOut[1:]
            for server in self.ircd.servers.itervalues():
                if server.nextClosest == self.ircd.serverID and server != fromServer:
                    server.sendMessage("MODE", channel.name, str(timestamp(channel.existedSince)), modeStr, *params, prefix=source)
    
    def sendUserModesToUsers(self, users, user, source, sourceName, modes):
        modeOuts = self.getOutputModes(modes)
        for modeOut in modeOuts:
            modeStr = modeOut[0]
            params = modeOut[1:]
            for u in set(users):
                u.sendMessage("MODE", modeStr, *params, prefix=sourceName, to=user.nick)
        del users[:]
    
    def sendUserModesToServers(self, user, source, sourceName, modes):
        modeOuts = self.getOutputModes(modes)
        
        if source[:3] == self.ircd.serverID:
            fromServer = None
        else:
            fromServer = self.ircd.servers[source[:3]]
            while fromServer.nextClosest != self.ircd.serverID:
                fromServer = self.ircd.servers[fromServer.nextClosest]
        for modeOut in modeOuts:
            modeStr = modeOut[0]
            params = modeOut[1:]
            for server in self.ircd.servers.itervalues():
                if server.nextClosest == self.ircd.serverID and server != fromServer:
                    server.sendMessage("MODE", user.uuid, str(timestamp(user.connectedSince)), modeStr, *params, prefix=source)
    
    def restrictUse(self, user, command, data):
        if "channel" not in data or "modes" not in data:
            return None
        if not data["params"]:
            for mode in data["modes"]:
                if mode != "+" and mode != "-" and (mode not in self.ircd.channelModeTypes or self.ircd.channelModeTypes[mode] != ModeType.List):
                    break
            else:
                return None # All the modes are list modes, and there are no parameters, so we're listing list mode parameters
        channel = data["channel"]
        if channel.userRank(user) < self.minLevel:
            user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, ":You do not have access to set channel modes")
            return False
        return None

class UserMode(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if not params or not params[0]:
            user.sendSingleError("ModeCmd", irc.ERR_NEEDMOREPARAMS, "MODE", ":Not enough parameters")
            return None
        channel = None
        if params[0] in self.ircd.channels:
            channel = self.ircd.channels[params[0]]
        elif params[0] in self.ircd.userNicks:
            if self.ircd.userNicks[params[0]] != user.uuid:
                user.sendSingleError("ModeCmd", irc.ERR_USERSDONTMATCH, ":Can't operate on modes for other users")
                return None
        else:
            user.sendSingleError("ModeCmd", irc.ERR_NOSUCHNICK, params[0], ":No such nick/channel")
            return None
        if len(params) == 1:
            if channel:
                return {
                    "channel": channel
                }
            return {}
        modeStr = params[1]
        modeParams = params[2:]
        if channel:
            return {
                "channel": channel,
                "modes": modeStr,
                "params": modeParams
            }
        return {
            "modes": modeStr,
            "params": modeParams
        }
    
    def affectedChannels(self, user, data):
        if "channel" in data:
            return [ data["channel"] ]
        return []
    
    def execute(self, user, data):
        if "modes" not in data:
            if "channel" in data:
                channel = data["channel"]
                user.sendMessage(irc.RPL_CHANNELMODEIS, channel.name, channel.modeString(user))
                user.sendMessage(irc.RPL_CREATIONTIME, channel.name, str(timestamp(channel.existedSince)))
                return True
            user.sendMessage(irc.RPL_UMODEIS, user.modeString(user))
            return True
        if "channel" in data:
            channel = data["channel"]
            channel.setModes(user.uuid, data["modes"], data["params"])
            return True
        user.setModes(user.uuid, data["modes"], data["params"])
        return True

class ServerMode(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) < 3:
            return None
        if prefix not in self.ircd.users and prefix not in self.ircd.servers:
            return None # It's safe to say other servers shouldn't be sending modes sourced from us. That's our job!
        if params[0] not in self.ircd.users and params[0] not in self.ircd.channels:
            return None
        try:
            return {
                "source": prefix,
                "target": params[0],
                "timestamp": int(params[1]),
                "modes": params[2],
                "params": params[3:]
            }
        except ValueError:
            return None
    
    def execute(self, server, data):
        source = data["source"]
        target = data["target"]
        targTS = data["timestamp"]
        if target in self.ircd.channels:
            channel = self.ircd.channels[target]
            if targTS > timestamp(channel.existedSince):
                return True
            if targTS < timestamp(channel.existedSince):
                # We need to remove all of the channel's modes
                while True: # Make a point to continue back to
                    modeStrList = []
                    params = []
                    for mode, param in channel.modes.iteritems():
                        if len(modeStrList) >= 20:
                            break
                        if self.ircd.channelModeTypes[mode] == ModeType.List:
                            for paramData in param:
                                modeStrList.append(mode)
                                params.append(paramData[0])
                                if len(modeStrList) >= 20:
                                    break
                        else:
                            modeStrList.append(mode)
                            if param is not None:
                                params.append(param)
                    for user, statusList in channel.users.iteritems():
                        for status in statusList:
                            if len(modeStrList) >= 20:
                                break
                            modeStrList.append(status)
                            params.append(user.nick)
                    if modeStrList:
                        channel.setModes(source, "-{}".format("".join(modeStrList)), params)
                    if channel.modes: # More processing is to be done
                        continue
                    for status in channel.users.itervalues():
                        if status:
                            break
                    else:
                        break # This one aborts the while True loop when we're done with modes
            channel.setModes(source, data["modes"], data["params"])
            return True
        user = self.ircd.users[target]
        if targTS > timestamp(user.connectedSince):
            return True
        if targTS < timestamp(user.connectedSince):
            while True:
                modeStrList = []
                params = []
                for mode, param in channel.modes.iteritems():
                    if len(modeStrList) >= 20:
                        break
                    if self.ircd.userModeTypes[mode] == ModeType.List:
                        for paramData in param:
                            modeStrList.append(mode)
                            params.append(paramData[0])
                            if len(modeStrList) >= 20:
                                break
                    else:
                        modeStrList.append(mode)
                        if param is not None:
                            params.append(param)
                if modeStrList:
                    user.setModes(source, "-{}".format("".join(modeStrList)), params)
                if not user.modes:
                    break
        user.setModes(source, data["modes"], data["params"])
        return True

modeCommand = ModeCommand()