from twisted.internet import reactor
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class DieCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "DieCommand"
	core = True
	
	def actions(self):
		return [ ("commandpermission-DIE", 1, self.checkCommandPermission) ]
	
	def userCommands(self):
		return [ ("DIE", 1, self) ]
	
	def checkCommandPermission(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-die", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def parseParams(self, user, params, prefix, tags):
		return {}
	
	def execute(self, user, data):
		reactor.stop()
		return True

dieCmd = DieCommand()