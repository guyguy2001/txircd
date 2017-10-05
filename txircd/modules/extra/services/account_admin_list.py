from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Callable, Dict, List, Tuple

@implementer(IPlugin, IModuleData)
class AccountAdminList(ModuleData):
	name = "AccountAdminList"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("statsruntype-accounts", 1, self.listAccounts) ]
	
	def listAccounts(self) -> Dict[str, str]:
		accountNameList = self.ircd.runActionUntilValue("accountlistallnames")
		if not accountNameList:
			return {}
		accountNames = {}
		for name in accountNameList:
			accountNames[name] = "*"
		return accountNames

accountAdminList = AccountAdminList()