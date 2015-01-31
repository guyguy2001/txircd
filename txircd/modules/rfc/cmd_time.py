from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import now
from zope.interface import implements

class TimeCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "TimeCommand"
	core = True
	
	def hookIRCd(self, ircd):
		self.ircd = ircd
	
	def actions(self):
		return [ ("sendremoteusermessage-391", 1, self.pushTime) ]
	
	def userCommands(self):
		return [ ("TIME", 1, UserTime(self.ircd, self.sendTime)) ]
	
	def serverCommands(self):
		return [ ("USERTIME", 1, ServerTime(self.ircd, self.sendTime)) ]
	
	def pushTime(self, user, *params, **kw):
		self.ircd.servers[user.uuid[:3]].sendMessage("PUSH", user.uuid[:3], "::{} {} {}".format(kw["prefix"], irc.RPL_TIME, " ".join(params)), prefix=self.ircd.serverID)
		return True
	
	def sendTime(self, user):
		user.sendMessage(irc.RPL_TIME, self.ircd.name, ":{}".format(now()))

class UserTime(Command):
	implements(ICommand)
	
	def __init__(self, ircd, sendTimeFunc):
		self.ircd = ircd
		self.sendTime = sendTimeFunc
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		if params[0] == self.ircd.name:
			return {}
		if params[0] not in self.ircd.serverNames:
			user.sendSingleError("TimeServer", irc.ERR_NOSUCHSERVER, params[0], ":No such server")
			return None
		return {
			"server": self.ircd.servers[self.ircd.serverNames[params[0]]]
		}
	
	def execute(self, user, data):
		if "server" in data:
			server = data["server"]
			server.sendMessage("USERTIME", server.serverID, prefix=user.uuid)
		else:
			self.sendTime(user)
		return True

class ServerTime(Command):
	implements(ICommand)
	
	def __init__(self, ircd, sendTimeFunc):
		self.ircd = ircd
		self.sendTime = sendTimeFunc
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if prefix not in self.ircd.users:
			return None
		if params[0] == self.ircd.serverID:
			return {
			"fromuser": self.ircd.users[prefix]
			}
		if params[0] not in self.ircd.serverNames:
			return None
		return {
			"server": self.ircd.servers[params[0]],
			"fromuser": self.ircd.users[prefix]
		}
	
	def execute(self, server, data):
		if "server" in data:
			server = data["server"]
			server.sendMessage("USERTIME", server.serverID, prefix=data["fromuser"].uuid)
		else:
			self.sendTime(data["fromuser"])
		return True

timeCmd = TimeCommand()