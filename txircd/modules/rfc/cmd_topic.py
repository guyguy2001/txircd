from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import timestamp
from zope.interface import implements
from datetime import datetime

irc.RPL_TOPICWHOTIME = "333"

class TopicCommand(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "TopicCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("topic", 1, self.onTopic),
                ("join", 2, self.sendChannelTopic) ]
    
    def userCommands(self):
        return [ ("TOPIC", 1, UserTopic(self.ircd, self)) ]
    
    def serverCommands(self):
        return [ ("TOPIC", 1, ServerTopic(self.ircd)) ]
    
    def onTopic(self, channel, setter, oldTopic):
        for user in channel.users.iterkeys():
            if user.uuid[:3] == self.ircd.serverID:
                user.sendMessage("TOPIC", ":{}".format(channel.topic), to=channel.name, prefix=channel.topicSetter)
        if setter in self.ircd.users and setter[:3] == self.ircd.serverID:
            settingUser = self.ircd.users[setter]
            if settingUser not in channel.users:
                settingUser.sendMessage("TOPIC", ":{}".format(channel.topic), to=channel.name, prefix=channel.topicSetter)
        elif setter == self.ircd.serverID:
            sourceServer = None
        else:
            sourceServer = self.ircd.servers[setter[:3]]
            while sourceServer.nextClosest != self.ircd.serverID:
                sourceServer = self.ircd.servers[sourceServer.nextClosest]
        for server in self.ircd.servers.itervalues():
            if server != sourceServer and server.nextClosest == self.ircd.serverID:
                server.sendMessage("TOPIC", channel.name, str(timestamp(channel.existedSince)), str(timestamp(channel.topicTime)), ":{}".format(channel.topic), prefix=setter)
    
    def sendChannelTopic(self, channel, user):
        if not channel.topic:
            user.sendMessage(irc.RPL_NOTOPIC, channel.name, ":No topic is set")
        else:
            user.sendMessage(irc.RPL_TOPIC, channel.name, ":{}".format(channel.topic))
            user.sendMessage(irc.RPL_TOPICWHOTIME, channel.name, channel.topicSetter, str(timestamp(channel.topicTime)))

class UserTopic(Command):
    implements(ICommand)
    
    def __init__(self, ircd, module):
        self.ircd = ircd
        self.module = module
    
    def parseParams(self, user, params, prefix, tags):
        if not params:
            user.sendCommandError(irc.ERR_NEEDMOREPARAMS, "TOPIC", ":Not enough parameters")
            return None
        if params[0] not in self.ircd.channels:
            user.sendCommandError(irc.ERR_NOSUCHCHANNEL, params[0], ":No such channel")
            return None
        channel = self.ircd.channels[params[0]]
        if len(params) == 1:
            return {
                "channel": channel
            }
        topic = params[1][:self.ircd.config.getWithDefault("topic_length",326)]
        return {
            "channel": channel,
            "topic": topic
        }
    
    def execute(self, user, data):
        if "topic" in data:
            data["channel"].setTopic(data["topic"], user.uuid)
        else:
            self.module.sendChannelTopic(data["channel"], user)
        return True

class ServerTopic(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 4:
            return None
        if params[0] not in self.ircd.channels:
            return None
        return {
            "source": prefix,
            "channel": self.ircd.channels[params[0]],
            "chantime": datetime.utcfromtimestamp(int(params[1])),
            "topictime": datetime.utcfromtimestamp(int(params[2])),
            "topic": params[3]
        }
    
    def execute(self, server, data):
        channel = data["channel"]
        if data["chantime"] > channel.existedSince: # Don't set the topic when our channel overrides
            return True # Assume handled by our ignoring of it
        if data["topictime"] <= channel.topicTime:
            return True # Don't set the topic when our topic overrides
        if channel.setTopic(data["topic"], data["source"]):
            return True
        return None

topicCommand = TopicCommand()