from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd import version
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class InfoCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "InfoCommand"
	core = True
	
	def userCommands(self):
		return [ ("INFO", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		return {}
	
	def execute(self, user, data):
		user.sendMessage(irc.RPL_INFO, "{} is running txircd-{}".format(self.ircd.name, version))
		user.sendMessage(irc.RPL_INFO, "Originally developed for the Desert Bus for Hope charity fundraiser (http://desertbus.org)")
		user.sendMessage(irc.RPL_INFO, ":")
		user.sendMessage(irc.RPL_INFO, "Developed by ElementalAlchemist <ElementAlchemist7@gmail.com>")
		user.sendMessage(irc.RPL_INFO, "Contributors:")
		user.sendMessage(irc.RPL_INFO, "   Heufneutje")
		user.sendMessage(irc.RPL_INFO, "   ekimekim")
		user.sendMessage(irc.RPL_ENDOFINFO, "End of /INFO list")
		return True

infoCmd = InfoCommand()