from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import timestampStringFromTime, timestampStringFromTimeSeconds, trimStringToByteLength
from zope.interface import implementer
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

irc.RPL_TOPICWHOTIME = "333"

@implementer(IPlugin, IModuleData)
class TopicCommand(ModuleData):
	name = "TopicCommand"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("topic", 1, self.onTopic),
		         ("join", 2, self.sendChannelTopic),
		         ("buildisupport", 1, self.buildISupport) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("TOPIC", 1, UserTopic(self.ircd, self)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("TOPIC", 1, ServerTopic(self.ircd)) ]

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "topic_length" in config:
			if not isinstance(config["topic_length"], int) or config["topic_length"] < 0:
				raise ConfigValidationError("topic_length", "invalid number")
			elif config["topic_length"] > 326:
				config["topic_length"] = 326
				self.ircd.logConfigValidationWarning("topic_length", "value is too large", 326)
	
	def onTopic(self, channel: "IRCChannel", setter: str, oldTopic: str):
		userSource = setter in self.ircd.users
		if userSource:
			sourceUser = self.ircd.users[setter]
			conditionalTags = {}
			self.ircd.runActionStandard("sendingusertags", sourceUser, conditionalTags)
		for user in channel.users.keys():
			if user.uuid[:3] == self.ircd.serverID:
				tags = {}
				if userSource:
					tags = user.filterConditionalTags(conditionalTags)
				user.sendMessage("TOPIC", channel.topic, to=channel.name, prefix=channel.topicSetter, tags=tags)
		sourceServer = None
		if userSource and setter[:3] == self.ircd.serverID:
			if sourceUser not in channel.users:
				tags = sourceUser.filterConditionalTags(conditionalTags)
				sourceUser.sendMessage("TOPIC", channel.topic, to=channel.name, prefix=channel.topicSetter, tags=tags)
		elif setter != self.ircd.serverID:
			sourceServer = self.ircd.servers[setter[:3]]
			while sourceServer.nextClosest != self.ircd.serverID:
				sourceServer = self.ircd.servers[sourceServer.nextClosest]
		self.ircd.broadcastToServers(sourceServer, "TOPIC", channel.name, timestampStringFromTime(channel.existedSince), timestampStringFromTime(channel.topicTime), channel.topic, prefix=setter)
	
	def sendChannelTopic(self, channel: "IRCChannel", user: "IRCUser", fromServer: Optional["IRCServer"]) -> None:
		if not channel.topic:
			user.sendMessage(irc.RPL_NOTOPIC, channel.name, "No topic is set")
		else:
			user.sendMessage(irc.RPL_TOPIC, channel.name, channel.topic)
			user.sendMessage(irc.RPL_TOPICWHOTIME, channel.name, channel.topicSetter, timestampStringFromTimeSeconds(channel.topicTime))

	def buildISupport(self, data: Dict[str, Union[str, int]]) -> None:
		data["TOPICLEN"] = self.ircd.config.get("topic_length", 326)

@implementer(ICommand)
class UserTopic(Command):
	def __init__(self, ircd, module):
		self.ircd = ircd
		self.module = module
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("TopicCmd", irc.ERR_NEEDMOREPARAMS, "TOPIC", "Not enough parameters")
			return None
		if params[0] not in self.ircd.channels:
			user.sendSingleError("TopicCmd", irc.ERR_NOSUCHCHANNEL, params[0], "No such channel")
			return None
		channel = self.ircd.channels[params[0]]
		if len(params) == 1:
			return {
				"channel": channel
			}
		topic = trimStringToByteLength(params[1], self.ircd.config.get("topic_length", 326))
		return {
			"channel": channel,
			"topic": topic
		}
	
	def affectedChannels(self, user: "IRCUser", data: Dict[Any, Any]) -> List["IRCChannel"]:
		return [ data["channel"] ]
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if "topic" in data:
			data["channel"].setTopic(data["topic"], user.uuid)
		else:
			self.module.sendChannelTopic(data["channel"], user)
		return True

@implementer(ICommand)
class ServerTopic(Command):
	burstQueuePriority = 79
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 4:
			return None
		if params[0] not in self.ircd.channels:
			if params[0] in self.ircd.recentlyDestroyedChannels:
				return {
					"lostchannel": True
				}
			return None
		try:
			return {
				"source": prefix,
				"channel": self.ircd.channels[params[0]],
				"chantime": datetime.utcfromtimestamp(float(params[1])),
				"topictime": datetime.utcfromtimestamp(float(params[2])),
				"topic": params[3]
			}
		except (TypeError, ValueError):
			return None
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostchannel" in data:
			return True
		channel = data["channel"]
		remoteChannelTime = data["chantime"]
		if remoteChannelTime > channel.existedSince: # Don't set the topic when our channel overrides
			return True # Assume handled by our ignoring of it
		if remoteChannelTime < channel.existedSince:
			channel.setCreationTime(remoteChannelTime)
		if channel.topic and data["topictime"] <= channel.topicTime:
			return True # Don't set the topic when our topic overrides
		if channel.setTopic(data["topic"], data["source"]):
			return True
		return False

topicCommand = TopicCommand()