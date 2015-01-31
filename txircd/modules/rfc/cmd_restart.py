from twisted.internet import reactor
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements
import os, sys

class RestartCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "RestartCommand"
	core = True
	
	def hookIRCd(self, ircd):
		self.ircd = ircd
	
	def actions(self):
		return [ ("commandpermission-RESTART", 1, self.checkRestartPermission) ]
	
	def userCommands(self):
		return [ ("RESTART", 1, self) ]
	
	def checkRestartPermission(self, user, command, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-restart", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def parseParams(self, user, params, prefix, tags):
		return {}
	
	def execute(self, user, data):
		reactor.addSystemEventTrigger("after", "shutdown", lambda: os.execl(sys.executable, sys.executable, *sys.argv))
		os.unlink("twistd.pid") # If we don't remove the pid file, the new twistd will refuse to start.
		reactor.stop()
		return True

restartCmd = RestartCommand()