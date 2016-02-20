from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class IsonCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "IsonCommand"
	core = True
	
	def userCommands(self):
		return [ ("ISON", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendSingleError("IsonParams", irc.ERR_NEEDMOREPARAMS, "ISON", "Not enough parameters")
			return None
		return {
			"nicks": params[:5]
		}
	
	def execute(self, user, data):
		onUsers = []
		for nick in data["nicks"]:
			if nick in self.ircd.userNicks:
				onUsers.append(self.ircd.userNicks[nick].nick)
		user.sendMessage(irc.RPL_ISON, " ".join(onUsers))
		return True

isonCmd = IsonCommand()