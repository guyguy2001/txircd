from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class SnoOper(ModuleData):
	implements(IPlugin, IModuleData)

	name = "ServerNoticeOper"
	core = True

	def hookIRCd(self, ircd):
		self.ircd = ircd

	def actions(self):
		return [ ("operreport", 1, self.sendOperNotice),
				("servernoticetype", 1, self.checkSnoType) ]

	def sendOperNotice(self, user, reason):
		if reason:
			message = "Failed OPER attempt from {} ({}).".format(user.nick, reason)
		else:
			message = "{} has opered.".format(user.nick)
		snodata = {
			"mask": "oper",
			"message": message
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)

	def checkSnoType(self, user, typename):
		return typename == "oper"

snoOper = SnoOper()