from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class PartCommand(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "PartCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("partmessage", 101, self.broadcastPart),
                ("partmessage", 1, self.sendPartMessage) ]
    
    def userCommands(self):
        return [ ("PART", 1, UserPart(self.ircd)) ]
    
    def serverCommands(self):
        return [ ("PART", 1, ServerPart(self.ircd)) ]
    
    def broadcastPart(self, sendUserList, channel, user, reason, fromServer):
        reason = ":{}".format(reason)
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID and server != fromServer:
                server.sendMessage("PART", channel.name, reason, prefix=user.uuid)
    
    def sendPartMessage(self, sendUserList, channel, user, reason, fromServer):
        reason = ":{}".format(reason)
        destServers = set()
        destClosestServers = set()
        for destUser in sendUserList:
            if destUser.uuid[:3] == self.ircd.serverID:
                destUser.sendMessage("PART", reason, to=channel.name, sourceuser=user)
        del sendUserList[:]

class UserPart(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if not params or not params[0]:
            user.sendSingleError("PartCmd", irc.ERR_NEEDMOREPARAMS, "PART", ":Not enough parameters")
            return None
        if params[0] not in self.ircd.channels:
            user.sendSingleError("PartCmd", irc.ERR_NOSUCHCHANNEL, params[0], ":No such channel")
            return None
        channel = self.ircd.channels[params[0]]
        if user not in channel.users:
            return None
        reason = params[1] if len(params) > 1 else ""
        reason = reason[:self.ircd.config.getWithDefault("part_message_length", 300)]
        return {
            "channel": channel,
            "reason": reason
        }
    
    def affectedChannels(self, user, data):
        return [ data["channel"] ]
    
    def execute(self, user, data):
        channel = data["channel"]
        reason = data["reason"]
        sendUserList = channel.users.keys()
        self.ircd.runActionProcessing("partmessage", sendUserList, channel, user, reason, None, users=sendUserList, channels=[channel])
        user.leaveChannel(channel)
        return True

class ServerPart(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 2 or not params[0]:
            return None
        if prefix not in self.ircd.users:
            return None
        if params[0] not in self.ircd.channels:
            return None
        return {
            "user": self.ircd.users[prefix],
            "channel": self.ircd.channels[params[0]],
            "reason": params[1]
        }
    
    def execute(self, server, data):
        user = data["user"]
        channel = data["channel"]
        reason = data["reason"]
        sendUserList = channel.users.keys()
        self.ircd.runActionProcessing("partmessage", sendUserList, channel, user, reason, server, users=sendUserList, channels=[channel])
        user.leaveChannel(channel, True)
        return True

partCommand = PartCommand()