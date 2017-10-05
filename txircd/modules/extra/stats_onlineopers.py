from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import now
from zope.interface import implementer
from typing import Callable, Dict, List, Tuple

@implementer(IPlugin, IModuleData)
class StatsOnlineOpers(ModuleData):
	name = "StatsOnlineOpers"

	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("statsruntype-onlineopers", 10, self.listOnlineOpers) ]

	def listOnlineOpers(self) -> Dict[str, str]:
		info = {}
		for user in self.ircd.users.values():
			if self.ircd.runActionUntilValue("userhasoperpermission", user, "", users=[user]):
				info[user.nick] = "{} ({}@{}) Idle: {} secs".format(user.nick, user.ident, user.host(), int((now() - user.idleSince).total_seconds()))
		return info

statsOnlineOpers = StatsOnlineOpers()