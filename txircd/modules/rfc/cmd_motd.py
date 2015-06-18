from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import splitMessage
from zope.interface import implements

class MessageOfTheDay(ModuleData, Command):
	implements(IPlugin, IModuleData)
	
	name = "MOTD"
	core = True
	motd = []
	remoteMOTD = {}
	
	def actions(self):
		return [ ("welcome", 5, self.showMOTD),
		         ("serverquit", 10, self.removeFromCache) ]
	
	def userCommands(self):
		return [ ("MOTD", 1, UserMOTD(self)) ]
	
	def serverCommands(self):
		return [ ("MOTDREQ", 1, ServerMOTDRequest(self)),
		         ("STARTMOTD", 1, ServerStartMOTD(self)),
		         ("MOTD", 1, ServerMOTD(self)),
		         ("ENDMOTD", 1, ServerEndMOTD(self)),
		         ("INVALIDATEMOTD", 1, RemoveMOTD(self)) ]
	
	def load(self):
		self.rehash()
	
	def rehash(self):
		self.motd = []
		try:
			with open(self.ircd.config["motd_file"], "r") as motdFile:
				for line in motdFile:
					for outputLine in splitMessage(line, 400):
						self.motd.append(outputLine)
		except KeyError:
			pass # The MOTD list is already in the condition such that it will be reported as "no MOTD," so we're fine here
		except IOError:
			self.ircd.log.error("Failed to open MOTD file") # But if a file was specified but couldn't be opened, we'll log an error
		self.ircd.broadcastToServers(None, "INVALIDATEMOTD", prefix=self.ircd.serverID)
	
	def showMOTD(self, user):
		if not self.motd:
			user.sendMessage(irc.ERR_NOMOTD, "Message of the day file is missing.")
		else:
			user.sendMessage(irc.RPL_MOTDSTART, "{} Message of the Day".format(self.ircd.name))
			for line in self.motd:
				user.sendMessage(irc.RPL_MOTD, line)
			user.sendMessage(irc.RPL_ENDOFMOTD, "End of message of the day")
	
	def showRemoteMOTD(self, user, server):
		if server.serverID not in self.remoteMOTD:
			return
		if not self.remoteMOTD[server.serverID][1]:
			return
		if not self.remoteMOTD[server.serverID][0]:
			user.sendMessage(irc.ERR_NOMOTD, "Message of the day file is missing.")
			return
		user.sendMessage(irc.RPL_MOTDSTART, "{} Message of the Day".format(server.name))
		for line in self.remoteMOTD[server.serverID][0]:
			user.sendMessage(irc.RPL_MOTD, line)
		user.sendMessage(irc.RPL_ENDOFMOTD, "End of message of the day")
	
	def removeFromCache(self, server, reason):
		if server.serverID in self.remoteMOTD:
			del self.remoteMOTD[server.serverID]

class UserMOTD(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user, params, prefix, tags):
		if params and params[0] != self.ircd.name:
			if params[0] not in self.ircd.serverNames:
				user.sendSingleError("MOTDServer", irc.ERR_NOSUCHSERVER, params[0], "No such server")
				return None
			return {
				"server": self.ircd.servers[self.ircd.serverNames[params[0]]]
			}
		return {}
	
	def execute(self, user, data):
		if not data:
			self.module.showMOTD(user, self.ircd.name)
			return True
		toServer = data["server"]
		toServer.sendMessage("MOTDREQ", toServer.serverID, prefix=user.uuid)
		return True

class ServerMOTDRequest(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if params[0] != self.ircd.serverID and params[0] not in self.ircd.servers:
			return None
		if prefix in self.ircd.users:
			if params[0] == self.ircd.serverID:
				return {
					"byuser": self.ircd.users[prefix]
				}
			return {
				"byuser": self.ircd.users[prefix],
				"destserver": self.ircd.servers[params[0]]
			}
		if prefix in self.ircd.servers:
			if params[0] == self.ircd.serverID:
				return {
					"byserver": self.ircd.servers[prefix]
				}
			return {
				"byserver": self.ircd.servers[prefix],
				"destserver": self.ircd.servers[params[0]]
			}
		return None
	
	def execute(self, server, data):
		if "byuser" in data:
			byUser = data["user"]
			fromServer = self.ircd.servers[byUser.uuid[:3]]
			byID = byUser.uuid
		elif "byserver" in data:
			fromServer = data["byserver"]
			byID = fromServer.serverID
		else:
			return None
		if "destserver" in data:
			toServer = data["destserver"]
			if toServer.serverID in self.module.remoteMOTD and self.module.remoteMOTD[toServer.serverID][1]:
				server.sendMessage("STARTMOTD", byID)
				for line in self.module.remoteMOTD[toServer.serverID][0]:
					server.sendMessage("MOTD", byID, line, prefix=toServer.serverID)
				server.sendMessage("ENDMOTD", byID, prefix=toServer.serverID)
				return True
			toServer.sendMessage("MOTDREQ", toServer.serverID, prefix=byID)
			return True
		server.sendMessage("STARTMOTD", byID)
		for line in self.module.motd:
			server.sendMessage("MOTD", byID, line, prefix=self.ircd.serverID)
		server.sendMessage("ENDMOTD", byID, prefix=self.ircd.serverID)
		return True

class ServerStartMOTD(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if prefix not in self.ircd.servers:
			return None
		if params[0] == "*":
			return {
				"fromserver": self.ircd.servers[prefix]
			}
		if params[0] in self.ircd.users:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destuser": self.ircd.users[params[0]]
			}
		if params[0] == self.ircd.serverID:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destserver": None
			}
		if params[0] in self.ircd.servers:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destserver": self.ircd.servers[params[0]]
			}
		return None
	
	def execute(self, server, data):
		fromServer = data["fromserver"]
		self.module.remoteMOTD[fromServer.serverID] = ([], False)
		if "destuser" in data:
			user = data["destuser"]
			if user.uuid[:3] == self.ircd.serverID:
				return True # We'll show them when we get ENDMOTD
			self.ircd.servers[user.uuid[:3]].sendMessage("STARTMOTD", user.uuid, prefix=fromServer.serverID)
			return True
		if "destserver" in data:
			toServer = data["destserver"]
			if toServer is None:
				return True # We already handle it before handling routing
			toServer.sendMessage("STARTMOTD", toServer.serverID, prefix=fromServer.serverID)
			return True
		self.ircd.broadcastToServers(server, "STARTMOTD", "*", prefix=fromServer.serverID)
		return True

class ServerMOTD(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		if prefix not in self.ircd.servers:
			return None
		if params[0] == "*":
			return {
				"fromserver": self.ircd.servers[prefix],
				"motdline": params[1]
			}
		if params[0] in self.ircd.users:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destuser": self.ircd.users[params[0]],
				"motdline": params[1]
			}
		if params[0] == self.ircd.serverID:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destserver": None,
				"motdline": params[1]
			}
		if params[0] in self.ircd.servers:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destserver": self.ircd.servers[params[0]],
				"motdline": params[1]
			}
		return None
	
	def execute(self, server, data):
		fromServer = data["fromserver"]
		newLine = data["motdline"]
		if fromServer.serverID in self.module.remoteMOTD and not self.module.remoteMOTD[fromServer.serverID][1]:
			self.module.remoteMOTD[fromServer.serverID][0].append(newLine)
		if "destuser" in data:
			user = data["destuser"]
			if user.uuid[:3] == self.ircd.serverID:
				return True # We'll show them when we get ENDMOTD
			self.ircd.servers[user.uuid[:3]].sendMessage("MOTD", user.uuid, newLine, prefix=fromServer.serverID)
			return True
		if "destserver" in data:
			toServer = data["destserver"]
			if toServer is None:
				return True # We handled it before we tried to handle routing, so all is good.
			toServer.sendMessage("MOTD", toServer.serverID, newLine, prefix=fromServer.serverID)
			return True
		self.ircd.broadcastToServers(server, "MOTD", "*", newLine, prefix=fromServer.serverID)
		return True

class ServerEndMOTD(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if prefix not in self.ircd.servers:
			return None
		if params[0] == "*":
			return {
				"fromserver": self.ircd.servers[prefix]
			}
		if params[0] in self.ircd.users:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destuser": self.ircd.users[params[0]]
			}
		if params[0] == self.ircd.serverID:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destserver": None
			}
		if params[0] in self.ircd.servers:
			return {
				"fromserver": self.ircd.servers[prefix],
				"destserver": self.ircd.servers[params[0]]
			}
		return None
	
	def execute(self, server, data):
		fromServer = data["fromserver"]
		if fromServer.serverID in self.module.remoteMOTD:
			self.module.remoteMOTD[fromServer.serverID] = (self.module.remoteMOTD[fromServer.serverID][0], True)
		else:
			self.module.remoteMOTD[fromServer.serverID] = ([], True)
		if "destuser" in data:
			user = data["destuser"]
			if user.uuid[:3] == self.ircd.serverID:
				self.module.showRemoteMOTD(user, fromServer)
				return True
			self.ircd.servers[user.uuid[:3]].sendMessage("ENDMOTD", user.uuid, prefix=fromServer.serverID)
			return True
		if "destserver" in data:
			toServer = data["destserver"]
			if toServer is None:
				return True # We handled it before we handled routing
			toServer.sendMessage("ENDMOTD", toServer.serverID, prefix=fromServer.serverID)
			return True
		self.ircd.broadcastToServers(server, "ENDMOTD", "*", prefix=fromServer.serverID)
		return True

class RemoveMOTD(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if prefix not in self.ircd.servers:
			return None
		return {
			"fromserver": self.ircd.servers[prefix]
		}
	
	def execute(self, server, data):
		fromServer = data["fromserver"]
		if fromServer.serverID in self.module.remoteMOTD:
			del self.module.remoteMOTD[fromServer.serverID]
		self.ircd.broadcastToServers(server, "INVALIDATEMOTD", prefix=fromServer.serverID)
		return True

motdHandler = MessageOfTheDay()