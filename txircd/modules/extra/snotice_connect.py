from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class SnoConnect(ModuleData):
	implements(IPlugin, IModuleData)

	name = "ServerNoticeConnect"

	def actions(self):
		return [ ("register", 1, self.sendConnectNotice),
				("servernoticetype", 1, self.checkSnoType)]

	def sendConnectNotice(self, user, *params):
		message =  "Client connected on {}: {} ({}) [{}]".format(self.ircd.name, user.hostmaskWithRealHost(), user.ip, user.gecos)
		snodata = {
			"mask": "connect",
			"message": message
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)
		return True

	def checkSnoType(self, user, typename):
		return typename == "connect"

snoConnect = SnoConnect()