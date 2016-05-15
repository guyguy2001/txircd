from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class QuitCommand(ModuleData, Command):
	implements(IPlugin, IModuleData)
	
	name = "QuitCommand"
	core = True
	
	def actions(self):
		return [ ("quitmessage", 10, self.sendQuitMessage),
		         ("remotequitrequest", 10, self.sendRQuit),
		         ("quit", 10, self.broadcastQuit),
		         ("remotequit", 10, self.broadcastQuit) ]
	
	def userCommands(self):
		return [ ("QUIT", 1, UserQuit(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("QUIT", 1, ServerQuit(self.ircd)) ]

	def verifyConfig(self, config):
		if "quit_message_length" in config:
			if not isinstance(config["quit_message_length"], int) or config["quit_message_length"] < 0:
				raise ConfigValidationError("quit_message_length", "invalid number")
			elif config["quit_message_length"] > 370:
				config["quit_message_length"] = 370
				self.ircd.logConfigValidationWarning("quit_message_length", "value is too large", 370)
	
	def sendQuitMessage(self, sendUserList, user, reason, batchName):
		hostmask = user.hostmask()
		conditionalTags = {}
		self.ircd.runActionStandard("sendingusertags", user, conditionalTags)
		for destUser in sendUserList:
			tags = destUser.filterConditionalTags(conditionalTags)
			if batchName:
				destUser.sendMessageInBatch(batchName, "QUIT", reason, to=None, prefix=hostmask, tags=tags)
			else:
				destUser.sendMessage("QUIT", reason, to=None, prefix=hostmask, tags=tags)
		del sendUserList[:]
	
	def sendRQuit(self, user, reason):
		self.ircd.servers[user.uuid[:3]].sendMessage("RQUIT", user.uuid, reason, prefix=self.ircd.serverID)
		return True
	
	def broadcastQuit(self, user, reason, fromServer = None):
		if user.isRegistered():
			self.ircd.broadcastToServers(fromServer, "QUIT", reason, prefix=user.uuid)

class UserQuit(Command):
	implements(ICommand)
	
	forRegistered = None
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params or not params[0]:
			return {
				"reason": None
			}
		return {
			"reason": params[0][:self.ircd.config.get("quit_message_length", 370)]
		}
	
	def execute(self, user, data):
		if data["reason"] is None:
			user.disconnect("Client quit")
		else:
			user.disconnect("Quit: {}".format(data["reason"]))
		return True

class ServerQuit(Command):
	implements(ICommand)
	
	burstQueuePriority = 81
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if prefix not in self.ircd.users:
			if prefix in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		if len(params) != 1:
			return None
		return {
			"user": self.ircd.users[prefix],
			"reason": params[0]
		}
	
	def execute(self, server, data):
		if "lostuser" not in data:
			data["user"].disconnect(data["reason"], server)
		return True

quitCommand = QuitCommand()