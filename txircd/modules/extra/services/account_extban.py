from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ircLower
from zope.interface import implements
from fnmatch import fnmatchcase

class AccountExtban(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountExtban"
	
	def actions(self):
		return [ ("usermatchban-R", 1, self.matchBan) ]
	
	def matchBan(self, user, matchNegated, mask):
		if not user.metadataKeyExists("account"):
			return matchNegated
		userAccount = ircLower(user.metadataValue("account"))
		if fnmatchcase(userAccount, mask):
			return not matchNegated
		return matchNegated

matchExtban = AccountExtban()