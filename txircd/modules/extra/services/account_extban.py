from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ircLower
from zope.interface import implements
from fnmatch import fnmatchcase

class AccountExtban(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountExtban"
	
	def actions(self):
		return [ ("usermatchban-R", 1, self.matchBan),
		  ("usermetadataupdate", 10, self.updateBansOnAccountChange) ]
	
	def matchBan(self, user, matchNegated, mask):
		if not user.metadataKeyExists("account"):
			return matchNegated
		userAccount = ircLower(user.metadataValue("account"))
		lowerMask = ircLower(mask)
		if fnmatchcase(userAccount, lowerMask):
			return not matchNegated
		return matchNegated
	
	def updateBansOnAccountChange(self, user, key, oldValue, value, fromServer = None):
		if key != "account":
			return
		self.ircd.runActionStandard("updateuserbancache", user)

matchExtban = AccountExtban()