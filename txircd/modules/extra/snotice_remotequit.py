from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class SnoRemoteQuit(ModuleData):
	implements(IPlugin, IModuleData)

	name = "ServerNoticeRemoteQuit"

	def actions(self):
		return [ ("remotequit", 1, self.sendRemoteQuitNotice),
				("servernoticetype", 1, self.checkSnoType)]

	def sendRemoteQuitNotice(self, user, reason):
		server = self.ircd.servers[user.uuid[:3]].name
		message =  "Client quit from {}: {} ({}) [{}]".format(server, user.hostmaskWithRealHost(), user.ip, reason)
		snodata = {
			"mask": "quit",
			"message": message
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)

	def checkSnoType(self, user, typename):
		return typename == "remotequit"

snoRemoteQuit = SnoRemoteQuit()