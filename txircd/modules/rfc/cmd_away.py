from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData, ICommand)
class AwayCommand(ModuleData, Command):
	name = "AwayCommand"
	core = True
	
	def userCommands(self):
		return [ ("AWAY", 1, self) ]
	
	def actions(self):
		return [ ("commandextra-PRIVMSG", 10, self.notifyAway),
		         ("commandextra-NOTICE", 10, self.notifyAway),
		         ("extrawhois", 10, self.addWhois),
		         ("buildisupport", 1, self.buildISupport),
		         ("usermetadataupdate", 10, self.sendAwayNotice) ]
	
	def verifyConfig(self, config):
		if "away_length" in config:
			if not isinstance(config["away_length"], int) or config["away_length"] < 0:
				raise ConfigValidationError("away_length", "invalid number")
			elif config["away_length"] > 200:
				config["away_length"] = 200
				self.ircd.logConfigValidationWarning("away_length", "value is too large", 200)
	
	def notifyAway(self, user, data):
		if "targetusers" not in data:
			return
		for u in data["targetusers"].keys():
			if u.metadataKeyExists("away"):
				user.sendMessage(irc.RPL_AWAY, u.nick, u.metadataValue("away"))
	
	def addWhois(self, user, targetUser):
		if targetUser.metadataKeyExists("away"):
			user.sendMessage(irc.RPL_AWAY, targetUser.nick, targetUser.metadataValue("away"))
	
	def buildISupport(self, data):
		data["AWAYLEN"] = self.ircd.config.get("away_length", 200)
	
	def sendAwayNotice(self, user, key, oldValue, value, fromServer):
		if key == "away":
			if value:
				user.sendMessage(irc.RPL_NOWAWAY, "You have been marked as being away")
			else:
				user.sendMessage(irc.RPL_UNAWAY, "You are no longer marked as being away")
	
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
			user.setMetadata("away", data["message"])
		else:
			user.setMetadata("away", None)
		return True

awayCommand = AwayCommand()