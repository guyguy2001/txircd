from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class SnoOper(ModuleData):
	implements(IPlugin, IModuleData)

	name = "ServerNoticeOper"
	core = True

	def actions(self):
		return [ ("oper", 1, self.sendOperNotice),
		         ("operfail", 1, self.sendOperFailNotice),
		         ("servernoticetype", 1, self.checkSnoType) ]
	
	def sendOperNotice(self, user):
		snodata = {
			"mask": "oper",
			"message": "{} has opered.".format(user.nick)
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)
	
	def sendOperFailNotice(self, user, reason):
		snodata = {
			"mask": "oper",
			"message": "Failed OPER attempt from {} ({})".format(user.nick, reason)
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)

	def checkSnoType(self, user, typename):
		return typename == "oper"

snoOper = SnoOper()