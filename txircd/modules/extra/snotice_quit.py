from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class SnoQuit(ModuleData):
	name = "ServerNoticeQuit"

	def actions(self):
		return [ ("quit", 1, self.sendQuitNotice),
		         ("servernoticetype", 1, self.checkSnoType)]

	def sendQuitNotice(self, user, reason, fromServer):
		if not user.isRegistered():
			return
		self.ircd.runActionStandard("sendservernotice", "quit", "Client quit from {}: {} ({}) [{}]".format(self.ircd.name, user.hostmaskWithRealHost(), user.ip, reason))

	def checkSnoType(self, user, typename):
		return typename == "quit"

snoQuit = SnoQuit()