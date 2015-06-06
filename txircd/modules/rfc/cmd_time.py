from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import now
from zope.interface import implements

class TimeCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "TimeCommand"
	core = True
	
	def userCommands(self):
		return [ ("TIME", 1, UserTime(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("USERTIMEREQ", 1, ServerTimeRequest(self.ircd)),
		         ("USERTIME", 1, ServerTime(self.ircd)) ]

class UserTime(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		if params[0] == self.ircd.name:
			return {}
		if params[0] not in self.ircd.serverNames:
			user.sendSingleError("TimeServer", irc.ERR_NOSUCHSERVER, params[0], "No such server")
			return None
		return {
			"server": self.ircd.servers[self.ircd.serverNames[params[0]]]
		}
	
	def execute(self, user, data):
		if "server" in data:
			server = data["server"]
			server.sendMessage("USERTIMEREQ", server.serverID, prefix=user.uuid)
		else:
			user.sendMessage(irc.RPL_TIME, self.ircd.name, str(now()))
		return True

class ServerTimeRequest(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if prefix not in self.ircd.users:
			return None
		if params[0] == self.ircd.serverID:
			return {
				"fromuser": self.ircd.users[prefix]
			}
		if params[0] not in self.ircd.servers:
			return None
		return {
			"server": self.ircd.servers[params[0]],
			"fromuser": self.ircd.users[prefix]
		}
	
	def execute(self, server, data):
		if "server" in data:
			destServer = data["server"]
			destServer.sendMessage("USERTIMEREQ", destServer.serverID, prefix=data["fromuser"].uuid)
		else:
			server.sendMessage("USERTIME", data["fromuser"].uuid, str(now()), prefix=self.ircd.serverID)
		return True

class ServerTime(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		if prefix not in self.ircd.servers:
			return None
		if params[0] not in self.ircd.users:
			return None
		return {
			"fromserver": self.ircd.servers[prefix],
			"touser": self.ircd.users[params[0]],
			"time": params[1]
		}
	
	def execute(self, server, data):
		fromServer = data["fromserver"]
		toUser = data["touser"]
		if toUser.uuid[:3] == self.ircd.serverID:
			toUser.sendMessage(irc.RPL_TIME, fromServer.name, data["time"])
			return True
		self.ircd.servers[toUser.uuid[:3]].sendMessage("USERTIME", toUser.uuid, data["time"], prefix=fromServer.serverID)
		return True

timeCmd = TimeCommand()