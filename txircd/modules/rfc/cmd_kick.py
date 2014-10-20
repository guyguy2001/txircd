from twisted.plugin import IPlugin
from twisted.python import log
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements
import logging

class KickCommand(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "KickCommand"
    core = True
    minLevel = 100
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("commandpermission-KICK", 10, self.checkKickLevel) ]
    
    def userCommands(self):
        return [ ("KICK", 1, UserKick(self.ircd)) ]
    
    def serverCommands(self):
        return [ ("KICK", 1, ServerKick(self.ircd)) ]
    
    def load(self):
        self.rehash()
    
    def rehash(self):
        newLevel = self.ircd.config.getWithDefault("channel_minimum_level_kick", 100)
        try:
            self.minLevel = int(newLevel)
        except ValueError:
            try:
                self.minLevel = self.ircd.channelStatuses[newLevel[0]][1]
            except KeyError:
                log.msg("KickCommand: No valid minimum level found; defaulting to 100", logLevel=logging.WARNING)
                self.minLevel = 100
    
    def checkKickLevel(self, user, command, data):
        channel = data["channel"]
        if user not in channel.users:
            user.sendMessage(irc.ERR_NOTONCHANNEL, channel.name, ":You're not on that channel")
            return False
        if channel.userRank(user) < self.minLevel:
            user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, ":You don't have permission to kick users from {}".format(channel.name))
            return False
        if channel.userRank(user) < channel.userRank(data["user"]):
            user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, ":You don't have permission to kick this user")
            return False
        return None


class UserKick(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if len(params) < 2:
            user.sendSingleError("KickCmd", irc.ERR_NEEDMOREPARAMS, "KICK", ":Not enough parameters")
            return None
        if params[0] not in self.ircd.channels:
            user.sendSingleError("KickCmd", irc.ERR_NOSUCHCHANNEL, params[0], ":No such channel")
            return None
        if params[1] not in self.ircd.userNicks:
            user.sendSingleError("KickCmd", irc.ERR_NOSUCHNICK, params[1], ":No such nick")
            return None
        channel = self.ircd.channels[params[0]]
        targetUser = self.ircd.users[self.ircd.userNicks[params[1]]]
        if targetUser not in channel.users:
            user.sendSingleError("KickCmd", irc.ERR_USERNOTINCHANNEL, targetUser.nick, channel.name, ":They are not on that channel")
            return None
        reason = user.nick
        if len(params) > 2:
            reason = params[2]
        return {
            "channel": channel,
            "user": targetUser,
            "reason": reason
        }
    
    def affectedUsers(self, user, data):
        return [data["user"]]
    
    def affectedChannels(self, user, data):
        return [data["channel"]]
    
    def execute(self, user, data):
        channel = data["channel"]
        targetUser = data["user"]
        reason = ":{}".format(data["reason"])
        for u in channel.users.iterkeys():
            if u.uuid[:3] == self.ircd.serverID:
                u.sendMessage("KICK", targetUser.nick, reason, sourceuser=user, to=channel.name)
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID:
                server.sendMessage("KICK", channel.name, targetUser.uuid, reason, prefix=user.uuid)
        targetUser.leaveChannel(channel)
        return True


class ServerKick(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 3:
            return None
        if prefix not in self.ircd.users:
            return None
        if params[0] not in self.ircd.channels:
            return None
        if params[1] not in self.ircd.users:
            return None
        return {
            "sourceuser": self.ircd.users[prefix],
            "channel": self.ircd.channels[params[0]],
            "targetuser": self.ircd.users[params[1]],
            "reason": params[2]
        }
    
    def execute(self, server, data):
        channel = data["channel"]
        sourceUser = data["sourceuser"]
        targetUser = data["targetuser"]
        reason = ":{}".format(data["reason"])
        
        for user in channel.users.iterkeys():
            if user.uuid[:3] == self.ircd.serverID:
                user.sendMessage("KICK", targetUser.nick, reason, sourceuser=sourceUser, to=channel.name)
        for remote in self.ircd.servers.itervalues():
            if remote != server and remote.nextClosest == self.ircd.serverID:
                remote.sendMessage("KICK", channel.name, targetUser.uuid, reason, prefix=sourceUser.uuid)
        targetUser.leaveChannel(channel, True)
        return True

kickCmd = KickCommand()