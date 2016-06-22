from twisted.plugin import IPlugin
from txircd.modbase import IModuleData, ModuleData
from zope.interface import implements

class SnoLinks(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ServerNoticeLinks"
	
	def actions(self):
		return [ ("serverconnect", 1, self.announceConnect),
		         ("serverquit", 1, self.announceQuit),
		         ("servernoticetype", 1, self.checkSnoType) ]
	
	def announceConnect(self, server):
		message = "Server {} ({}) connected (to {})".format(server.name, server.serverID, self.ircd.name if server.nextClosest == self.ircd.serverID else self.ircd.servers[server.nextClosest].name)
		self.ircd.runActionStandard("sendservernotice", "links", message)
	
	def announceQuit(self, server, reason):
		message = "Server {} ({}) disconnected (from {}) ({})".format(server.name, server.serverID, self.ircd.name if server.nextClosest == self.ircd.serverID else self.ircd.servers[server.nextClosest].name, reason)
		self.ircd.runActionStandard("sendservernotice", "links", message)
	
	def checkSnoType(self, user, typename):
		if typename == "links":
			return True
		return False

snoLinks = SnoLinks()