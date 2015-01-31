from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class SnoRemoteConnect(ModuleData):
	implements(IPlugin, IModuleData)

	name = "ServerNoticeRemoteConnect"
	core = True

	def hookIRCd(self, ircd):
		self.ircd = ircd

	def actions(self):
		return [ ("remoteregister", 1, self.sendRemoteConnectNotice),
				("servernoticetype", 1, self.checkSnoType)]

	def sendRemoteConnectNotice(self, user, *params):
		server = self.ircd.servers[user.uuid[:3]].name
		message =  "Client connected on {}: {} ({}) [{}]".format(server, user.hostmaskWithRealHost(), user.ip, user.gecos)
		snodata = {
			"mask": "connect",
			"message": message
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)

	def checkSnoType(self, user, typename):
		return typename == "remoteconnect"

snoRemoteConnect = SnoRemoteConnect()