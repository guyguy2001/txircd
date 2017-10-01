from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class SnoXLine(ModuleData):
	name = "ServerNoticeXLine"

	def actions(self):
		return [ ("addxline", 1, self.announceAdd),
		         ("delxline", 1, self.announceRemove),
		         ("servernoticetype", 1, self.checkSnoType) ]

	def announceAdd(self, lineType, mask, duration, setter, reason):
		message = "{} added {} x:line of type {} for {}{} ({})".format(setter, "permanent" if duration == 0 else "timed", lineType, mask, ", to expire in {} seconds".format(duration) if duration > 0 else "", reason)
		self.ircd.runActionStandard("sendservernotice", "xline", message)

	def announceRemove(self, lineType, mask, setter):
		message = "{} removed x:line of type {} for {}".format(setter, lineType, mask)
		self.ircd.runActionStandard("sendservernotice", "xline", message)

	def checkSnoType(self, user, typename):
		if typename == "xline":
			return True
		return False

snoXline = SnoXLine()