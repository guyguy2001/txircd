from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import splitMessage
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class MessageCommands(ModuleData):
	name = "MessageCommands"
	core = True
	
	def userCommands(self):
		return [ ("PRIVMSG", 1, UserPrivmsg(self)),
		         ("NOTICE", 1, UserNotice(self)) ]
	
	def serverCommands(self):
		return [ ("PRIVMSG", 1, ServerPrivmsg(self)),
		         ("NOTICE", 1, ServerNotice(self)) ]
	
	def verifyConfig(self, config):
		if "message_length" in config:
			if not isinstance(config["message_length"], int) or config["message_length"] < 0:
				raise ConfigValidationError("message_length", "invalid number")
			elif config["message_length"] > 324:
				config["message_length"] = 324
				self.ircd.logConfigValidationWarning("message_length", "value is too large", 324)
			elif config["message_length"] < 100:
				config["message_length"] = 100
				self.ircd.logConfigValidationWarning("message_length", "value is too small to be useful", 100)
		else:
			config["message_length"] = 324
	
	def cmdParseParams(self, user, params, prefix, tags):
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
	
	def cmdExecute(self, command, user, data):
		sentAMessage = False
		sentNoTextError = False
		userPrefix = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		if "targetusers" in data:
			for target, message in data["targetusers"].items():
				if message:
					if target.uuid[:3] == self.ircd.serverID:
						messageParts = splitMessage(message, self.ircd.config["message_length"])
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
					messageParts = splitMessage(message, self.ircd.config["message_length"])
					for part in messageParts:
						target.sendUserMessage(command, part, to=target.name, prefix=userPrefix, skip=[user], conditionalTags=conditionalTags, alwaysPrefixLastParam=True)
					target.sendServerMessage(command, target.name, message, prefix=user.uuid)
					sentAMessage = True
				elif not sentNoTextError:
					user.sendMessage(irc.ERR_NOTEXTTOSEND, "No text to send")
					sentNoTextError = True
		if not sentAMessage:
			return None
		return True
	
	def serverParseParams(self, server, params, prefix, tags):
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
	
	def serverExecute(self, command, server, data):
		if "lostsource" in data or "losttarget" in data:
			return True
		fromUser = data["from"]
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", fromUser, conditionalTags)
		if "touser" in data:
			user = data["touser"]
			if user.uuid[:3] == self.ircd.serverID:
				messageParts = splitMessage(data["message"], self.ircd.config["message_length"])
				tags = user.filterConditionalTags(conditionalTags)
				for part in messageParts:
					user.sendMessage(command, part, prefix=data["from"].hostmask(), tags=tags, alwaysPrefixLastParam=True)
			else:
				self.ircd.servers[user.uuid[:3]].sendMessage(command, user.uuid, data["message"], prefix=data["from"].uuid)
			return True
		if "tochan" in data:
			chan = data["tochan"]
			fromUser = data["from"]
			message = data["message"]
			messageParts = splitMessage(message, self.ircd.config["message_length"])
			for part in messageParts:
				chan.sendUserMessage(command, part, prefix=fromUser.hostmask(), conditionalTags=conditionalTags, alwaysPrefixLastParam=True)
			chan.sendServerMessage(command, chan.name, message, prefix=fromUser.uuid, skiplocal=[server])
			return True
		return None

@implementer(ICommand)
class UserPrivmsg(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("PrivMsgCmd", irc.ERR_NEEDMOREPARAMS, "PRIVMSG", "Not enough parameters")
			return None
		return self.module.cmdParseParams(user, params, prefix, tags)
	
	def affectedUsers(self, user, data):
		if "targetusers" in data:
			return list(data["targetusers"].keys())
		return []
	
	def affectedChannels(self, user, data):
		if "targetchans" in data:
			return list(data["targetchans"].keys())
		return []
	
	def execute(self, user, data):
		return self.module.cmdExecute("PRIVMSG", user, data)

@implementer(ICommand)
class UserNotice(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("NoticeCmd", irc.ERR_NEEDMOREPARAMS, "NOTICE", "Not enough parameters")
			return None
		return self.module.cmdParseParams(user, params, prefix, tags)
	
	def affectedUsers(self, user, data):
		if "targetusers" in data:
			return list(data["targetusers"].keys())
		return []
	
	def affectedChannels(self, user, data):
		if "targetchans" in data:
			return list(data["targetchans"].keys())
		return []
	
	def execute(self, user, data):
		return self.module.cmdExecute("NOTICE", user, data)

@implementer(ICommand)
class ServerPrivmsg(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.serverParseParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.serverExecute("PRIVMSG", server, data)

@implementer(ICommand)
class ServerNotice(Command):
	def __init__(self, module):
		self.module = module
	
	def parseParams(self, server, params, prefix, tags):
		return self.module.serverParseParams(server, params, prefix, tags)
	
	def execute(self, server, data):
		return self.module.serverExecute("NOTICE", server, data)

msgCommands = MessageCommands()