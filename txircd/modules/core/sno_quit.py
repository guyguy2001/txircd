from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class SnoQuit(ModuleData):
	implements(IPlugin, IModuleData)

	name = "ServerNoticeQuit"
	core = True

	def hookIRCd(self, ircd):
		self.ircd = ircd

	def actions(self):
		return [ ("quit", 1, self.sendQuitNotice),
				("servernoticetype", 1, self.checkSnoType)]

	def sendQuitNotice(self, user, reason):
		message =  "Client quit from {}: {} ({}) [{}]".format(self.ircd.name, user.hostmaskWithRealHost(), user.ip, reason)
		snodata = {
			"mask": "quit",
			"message": message
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)

	def checkSnoType(self, user, typename):
		return typename == "quit"

snoQuit = SnoQuit()