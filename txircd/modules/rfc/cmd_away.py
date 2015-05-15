from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class AwayCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "AwayCommand"
	core = True
	
	def userCommands(self):
		return [ ("AWAY", 1, self) ]
	
	def actions(self):
		return [ ("commandextra-PRIVMSG", 10, self.notifyAway),
				("commandextra-NOTICE", 10, self.notifyAway),
				("extrawhois", 10, self.addWhois) ]
	
	def notifyAway(self, user, data):
		if "targetusers" not in data:
			return
		for u in data["targetusers"].iterkeys():
			if u.metadataKeyExists("away"):
				user.sendMessage(irc.RPL_AWAY, u.nick, u.metadataValue("away"))
	
	def addWhois(self, user, targetUser):
		if targetUser.metadataKeyExists("away"):
			user.sendMessage(irc.RPL_AWAY, targetUser.nick, targetUser.metadataValue("away"))
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		message = " ".join(params)
		message = message[:self.ircd.config.get("away_length", 200)]
		return {
			"message": message
		}
	
	def execute(self, user, data):
		if "message" in data and data["message"]:
			user.setMetadata("away", data["message"], "*", False)
			user.sendMessage(irc.RPL_NOWAWAY, "You have been marked as being away")
		else:
			user.setMetadata("away", None, "*", False)
			user.sendMessage(irc.RPL_UNAWAY, "You are no longer marked as being away")
		return True

awayCommand = AwayCommand()