from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd import version
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData, ICommand)
class VersionCommand(ModuleData, Command):
	name = "VersionCommand"
	core = True
	
	def userCommands(self):
		return [ ("VERSION", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		return {}
	
	def execute(self, user, data):
		user.sendMessage(irc.RPL_VERSION, "txircd-{} {}".format(version, self.ircd.name))
		user.sendISupport()
		return True

versionCmd = VersionCommand()