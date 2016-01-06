from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class SnoOper(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerNoticeOper"
	
	def actions(self):
		return [ ("oper", 1, self.sendOperNotice),
		         ("operfail", 1, self.sendOperFailNotice),
		         ("servernoticetype", 1, self.checkSnoType) ]
	
	def serverCommands(self):
		return [ ("OPERFAILNOTICE", 1, self) ]
	
	def sendOperNotice(self, user):
		if user.uuid[:3] == self.ircd.serverID:
			snodata = {
				"mask": "oper",
				"message": "{} has opered.".format(user.nick)
			}
		else:
			snodata = {
				"mask": "remoteoper",
				"message": "{} has opered. (from {})".format(user.nick, self.ircd.servers[user.uuid[:3]].name)
			}
		self.ircd.runActionProcessing("sendservernotice", snodata)
	
	def sendOperFailNotice(self, user, reason):
		snodata = {
			"mask": "oper",
			"message": "Failed OPER attempt from {} ({})".format(user.nick, reason)
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)
		self.ircd.broadcastToServers(None, "OPERFAILNOTICE", user.uuid, reason, prefix=self.ircd.serverID)
	
	def checkSnoType(self, user, typename):
		if typename == "oper":
			return True
		if typename == "remoteoper":
			return True
		return False
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		if prefix not in self.ircd.servers:
			return None
		if params[0] not in self.ircd.users:
			# Since this should always come from the server the user is on, we don't need to worry about recently quit users
			return None
		return {
			"fromserver": self.ircd.servers[prefix],
			"user": self.ircd.users[params[0]],
			"reason": params[1]
		}
	
	def execute(self, server, data):
		user = data["user"]
		reason = data["reason"]
		fromServer = data["fromserver"]
		snodata = {
			"mask": "remoteoper",
			"message": "Failed OPER attempt from {} ({}) (from {})".format(user.nick, reason, fromServer.name)
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)
		self.ircd.broadcastToServers(server, "OPERFAILNOTICE", user.uuid, reason, prefix=fromServer.serverID)
		return True

snoOper = SnoOper()