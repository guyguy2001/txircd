from twisted.internet import reactor
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
import os, sys

@implementer(IPlugin, IModuleData, ICommand)
class RestartCommand(ModuleData, Command):
	name = "RestartCommand"
	core = True
	
	def actions(self):
		return [ ("commandpermission-RESTART", 1, self.checkRestartPermission) ]
	
	def userCommands(self):
		return [ ("RESTART", 1, self) ]
	
	def checkRestartPermission(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-restart", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def parseParams(self, user, params, prefix, tags):
		return {}
	
	def execute(self, user, data):
		self.ircd.log.info("Received RESTART command from user {user.uuid} ({user.nick})", user=user)
		reactor.addSystemEventTrigger("after", "shutdown", lambda: os.execl(sys.executable, sys.executable, *sys.argv))
		os.unlink("twistd.pid") # If we don't remove the pid file, the new twistd will refuse to start.
		reactor.stop()
		return True

restartCmd = RestartCommand()