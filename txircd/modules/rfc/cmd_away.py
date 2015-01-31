from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class AwayCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "AwayCommand"
	core = True
	
	def hookIRCd(self, ircd):
		self.ircd = ircd
	
	def userCommands(self):
		return [ ("AWAY", 1, self) ]
	
	def actions(self):
		return [ ("commandextra-PRIVMSG", 10, self.notifyAway),
				("commandextra-NOTICE", 10, self.notifyAway),
				("extrawhois", 10, self.addWhois) ]
	
	def notifyAway(self, user, command, data):
		if "targetusers" not in data:
			return
		for u in data["targetusers"].iterkeys():
			if "away" in u.metadata["ext"]:
				user.sendMessage(irc.RPL_AWAY, u.nick, ":{}".format(u.metadata["ext"]["away"]))
	
	def addWhois(self, user, targetUser):
		if "away" in targetUser.metadata["ext"]:
			user.sendMessage(irc.RPL_AWAY, targetUser.nick, ":{}".format(targetUser.metadata["ext"]["away"]))
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		return {
			"message": " ".join(params)
		}
	
	def execute(self, user, data):
		if "message" in data and data["message"]:
			user.setMetadata("ext", "away", data["message"])
			user.sendMessage(irc.RPL_NOWAWAY, ":You have been marked as being away")
		else:
			user.setMetadata("ext", "away", None)
			user.sendMessage(irc.RPL_UNAWAY, ":You are no longer marked as being away")
		return True

awayCommand = AwayCommand()