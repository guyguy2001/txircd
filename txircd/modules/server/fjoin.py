from twisted.plugin import IPlugin
from txircd.channel import IRCChannel
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType
from zope.interface import implements
from datetime import datetime

class FJoinCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "FJoinCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def serverCommands(self):
        return [ ("FJOIN", 1, self) ]
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) < 4:
            return None
        try:
            time = datetime.utcfromtimestamp(int(params[1]))
        except ValueError:
            return None
        modes = {}
        currParam = 3
        for mode in params[2]:
            if mode == "+":
                continue
            if mode not in self.ircd.channelModeTypes or self.ircd.channelModeTypes[mode] == ModeType.Status:
                return None
            modeType = self.ircd.channelModeTypes[mode]
            if modeType in (ModeType.ParamOnUnset, ModeType.Param):
                try:
                    modes[mode] = params[currParam]
                except IndexError:
                    return None
                currParam += 1
            else:
                modes[mode] = None
        try:
            usersInChannel = params[currParam].split()
        except IndexError:
            return None
        if currParam + 1 < len(params):
            return None
        users = {}
        try:
            for userData in usersInChannel:
                ranks, uuid = userData.split(",")
                if uuid not in self.ircd.users:
                    return None
                for rank in ranks:
                    if rank not in self.ircd.channelModeTypes or self.ircd.channelModeTypes[rank] != ModeType.Status:
                        return None
                users[self.ircd.users[uuid]] = ranks
        except ValueError:
            return None
        if params[0] in self.ircd.channels:
            channel = self.ircd.channels[params[0]]
        else:
            channel = IRCChannel(self.ircd, params[0])
        return {
            "channel": channel,
            "time": time,
            "modes": modes,
            "users": users
        }
    
    def execute(self, server, data):
        channel = data["channel"]
        time = data["time"]
        remoteModes = data["modes"]
        remoteStatuses = []
        for user, ranks in data["users"].iteritems():
            user.joinChannel(channel, True)
            for rank in ranks:
                remoteStatuses.append((user.nick, rank))
        if time < channel.existedSince:
            localModes = []
            localModeParams = []
            for mode, param in channel.modes.iteritems():
                modeType = self.ircd.channelModeTypes[mode]
                if modeType == ModeType.List:
                    for paramData in param:
                        localModes.append(mode)
                        localModeParams.append(paramData[0])
                        if len(localModes) == 20:
                            channel.setModes(self.ircd.serverID, "-{}".format("".join(localModes)), localModeParams)
                            localModes = []
                            localModeParams = []
                else:
                    localModes.append(mode)
                    if param is not None:
                        localModeParams.append(param)
                    if len(localModes) == 20:
                        channel.setModes(self.ircd.serverID, "-{}".format("".join(localModes)), localModeParams)
                        localModes = []
                        localModeParams = []
            for user, ranks in channel.users.iteritems():
                for rank in ranks:
                    localModes.append(rank)
                    localModeParams.append(user.nick)
                    if len(localModes) == 20:
                        channel.setModes(self.ircd.serverID, "-{}".format("".join(localModes)), localModeParams)
                        localModes = []
                        localModeParams = []
            if localModes:
                channel.setModes(self.ircd.serverID, "-{}".format("".join(localModes)), localModeParams)
            channel.existedSince = time
        if time == channel.existedSince:
            newModes = []
            newModeParams = []
            for mode, param in remoteModes.iteritems():
                newModes.append(mode)
                if param is not None:
                    newModeParams.append(param)
                if len(newModes) == 20:
                    channel.setModes(self.ircd.serverID, "+{}".format("".join(newModes)), newModeParams)
                    newModes = []
                    newModeParams = []
            for status in remoteStatuses:
                newModes.append(status[0])
                newModeParams.append(status[1])
                if len(newModes) == 20:
                    channel.setModes(self.ircd.serverID, "+{}".format("".join(newModes)), newModeParams)
                    newModes = []
                    newModeParams = []
            if newModes:
                channel.setModes(self.ircd.serverID, "+{}".format("".join(newModes)), newModeParams)
        return True

fjoinCmd = FJoinCommand()