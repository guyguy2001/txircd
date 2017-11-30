from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import lenBytes, splitMessage
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class MessageCommands(ModuleData):
	name = "MessageCommands"
	core = True
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("PRIVMSG", 1, UserPrivmsg(self)),
		         ("NOTICE", 1, UserNotice(self)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("PRIVMSG", 1, ServerPrivmsg(self)),
		         ("NOTICE", 1, ServerNotice(self)) ]
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "message_length" in config:
			if config["message_length"] is None:
				return
			if not isinstance(config["message_length"], int) or config["message_length"] < 0:
				raise ConfigValidationError("message_length", "invalid number")
			elif config["message_length"] > 324:
				config["message_length"] = None
				self.ircd.logConfigValidationWarning("message_length", "value is too large", 324)
			elif config["message_length"] < 100:
				config["message_length"] = 100
				self.ircd.logConfigValidationWarning("message_length", "value is too small to be useful", 100)
		else:
			config["message_length"] = None
	
	def cmdParseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		channels = []
		users = []
		user.startErrorBatch("MsgCmd")
		for target in params[0].split(","):
			if target in self.ircd.channels:
				channels.append(self.ircd.channels[target])
			elif target in self.ircd.userNicks:
				users.append(self.ircd.userNicks[target])
			else:
				user.sendBatchedError("MsgCmd", irc.ERR_NOSUCHNICK, target, "No such nick/channel")
		message = params[1]
		chanMessages = {target: message for target in channels}
		userMessages = {target: message for target in users}
		data = {}
		if channels:
			data["targetchans"] = chanMessages
		if users:
			data["targetusers"] = userMessages
		if data:
			return data
		return None
	
	def cmdExecute(self, command: str, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		sentAMessage = False
		sentNoTextError = False
		userPrefix = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		messageLen = self.ircd.config["message_length"]
		dynamicLen = False
		if messageLen is None:
			dynamicLen = True
			# 505 = 512 - message terminator (CRLF) - " :" to begin message - other spaces in line - : to begin prefix
			messageLen = 505 - lenBytes(userPrefix) - lenBytes(command)
		if "targetusers" in data:
			for target, message in data["targetusers"].items():
				if message:
					if target.uuid[:3] == self.ircd.serverID:
						thisMessageLen = messageLen
						if dynamicLen:
							thisMessageLen -= len(target.nick)
						messageParts = splitMessage(message, thisMessageLen)
						tags = target.filterConditionalTags(conditionalTags)
						for part in messageParts:
							target.sendMessage(command, part, prefix=userPrefix, tags=tags, alwaysPrefixLastParam=True)
					else:
						self.ircd.servers[target.uuid[:3]].sendMessage(command, target.uuid, message, prefix=user.uuid)
					sentAMessage = True
				elif not sentNoTextError:
					user.sendMessage(irc.ERR_NOTEXTTOSEND, "No text to send")
					sentNoTextError = True
		if "targetchans" in data:
			for target, message in data["targetchans"].items():
				if message:
					thisMessageLen = messageLen
					if dynamicLen:
						thisMessageLen -= len(target.name)
					messageParts = splitMessage(message, thisMessageLen)
					for part in messageParts:
						target.sendUserMessage(command, part, to=target.name, prefix=userPrefix, skip=[user], conditionalTags=conditionalTags, alwaysPrefixLastParam=True)
					target.sendServerMessage(command, target.name, message, prefix=user.uuid)
					sentAMessage = True
				elif not sentNoTextError:
					user.sendMessage(irc.ERR_NOTEXTTOSEND, "No text to send")
					sentNoTextError = True
		if not sentAMessage:
			return False
		return True
	
	def serverParseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		if prefix not in self.ircd.users:
			if prefix in self.ircd.recentlyQuitUsers:
				return {
					"lostsource": True
				}
			return None
		if params[0] in self.ircd.users:
			return {
				"from": self.ircd.users[prefix],
				"touser": self.ircd.users[params[0]],
				"message": params[1]
			}
		if params[0] in self.ircd.channels:
			return {
				"from": self.ircd.users[prefix],
				"tochan": self.ircd.channels[params[0]],
				"message": params[1]
			}
		if params[0] in self.ircd.recentlyQuitUsers or params[0] in self.ircd.recentlyDestroyedChannels:
			return {
				"losttarget": True
			}
		return None
	
	def serverExecute(self, command: str, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostsource" in data or "losttarget" in data:
			return True
		fromUser = data["from"]
		userPrefix = fromUser.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", fromUser, conditionalTags)
		messageLen = self.ircd.config["message_length"]
		dynamicLen = False
		if messageLen is None:
			dynamicLen = True
			# 505 = 512 - message terminator (CRLF) - " :" to begin message - other spaces in line - : to begin prefix
			messageLen = 505 - lenBytes(userPrefix) - lenBytes(command)
		if "touser" in data:
			user = data["touser"]
			if user.uuid[:3] == self.ircd.serverID:
				if dynamicLen:
					messageLen -= len(user.nick)
				messageParts = splitMessage(data["message"], messageLen)
				tags = user.filterConditionalTags(conditionalTags)
				for part in messageParts:
					user.sendMessage(command, part, prefix=userPrefix, tags=tags, alwaysPrefixLastParam=True)
			else:
				self.ircd.servers[user.uuid[:3]].sendMessage(command, user.uuid, data["message"], prefix=data["from"].uuid)
			return True
		elif "tochan" in data:
			chan = data["tochan"]
			fromUser = data["from"]
			message = data["message"]
			if dynamicLen:
				messageLen -= len(chan.name)
			messageParts = splitMessage(message, messageLen)
			for part in messageParts:
				chan.sendUserMessage(command, part, prefix=userPrefix, conditionalTags=conditionalTags, alwaysPrefixLastParam=True)
			chan.sendServerMessage(command, chan.name, message, prefix=fromUser.uuid, skiplocal=[server])
			return True
		return False

@implementer(ICommand)
class UserPrivmsg(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 2:
			user.sendSingleError("PrivMsgCmd", irc.ERR_NEEDMOREPARAMS, "PRIVMSG", "Not enough parameters")
			return None
		return self.module.cmdParseParams(user, params, prefix, tags)
	
	def affectedUsers(self, user: "IRCUser", data: Dict[Any, Any]) -> List["IRCUser"]:
		if "targetusers" in data:
			return list(data["targetusers"].keys())
		return []
	
	def affectedChannels(self, user: "IRCUser", data: Dict[Any, Any]) -> List["IRCChannel"]:
		if "targetchans" in data:
			return list(data["targetchans"].keys())
		return []
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		return self.module.cmdExecute("PRIVMSG", user, data)

@implementer(ICommand)
class UserNotice(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 2:
			user.sendSingleError("NoticeCmd", irc.ERR_NEEDMOREPARAMS, "NOTICE", "Not enough parameters")
			return None
		return self.module.cmdParseParams(user, params, prefix, tags)
	
	def affectedUsers(self, user: "IRCUser", data: Dict[Any, Any]) -> List["IRCUser"]:
		if "targetusers" in data:
			return list(data["targetusers"].keys())
		return []
	
	def affectedChannels(self, user: "IRCUser", data: Dict[Any, Any]) -> List["IRCChannel"]:
		if "targetchans" in data:
			return list(data["targetchans"].keys())
		return []
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		return self.module.cmdExecute("NOTICE", user, data)

@implementer(ICommand)
class ServerPrivmsg(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.serverParseParams(server, params, prefix, tags)
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		return self.module.serverExecute("PRIVMSG", server, data)

@implementer(ICommand)
class ServerNotice(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return self.module.serverParseParams(server, params, prefix, tags)
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		return self.module.serverExecute("NOTICE", server, data)

msgCommands = MessageCommands()