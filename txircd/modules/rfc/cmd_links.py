from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class LinksCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "LinksCommand"
	core = True
	
	def userCommands(self):
		return [ ("LINKS", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		return {}
	
	def execute(self, user, data):
		for server in self.ircd.servers.itervalues():
			hopCount = 1
			nextServer = server.nextClosest
			while nextServer != self.ircd.serverID:
				nextServer = self.ircd.servers[nextServer].nextClosest
				hopCount += 1
			if server.nextClosest == self.ircd.serverID:
				nextClosestName = self.ircd.name
			else:
				nextClosestName = self.ircd.servers[server.nextClosest].name
			user.sendMessage(irc.RPL_LINKS, server.name, nextClosestName, "{} {}".format(hopCount, server.description))
		user.sendMessage(irc.RPL_LINKS, self.ircd.name, self.ircd.name, "0 {}".format(self.ircd.config["server_description"]))
		user.sendMessage(irc.RPL_ENDOFLINKS, "*", "End of /LINKS list.")
		return True

linksCmd = LinksCommand()