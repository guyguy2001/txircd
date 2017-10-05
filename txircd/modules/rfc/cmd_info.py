from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd import version
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class InfoCommand(ModuleData, Command):
	name = "InfoCommand"
	core = True
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("INFO", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		user.sendMessage(irc.RPL_INFO, "{} is running txircd-{}".format(self.ircd.name, version))
		user.sendMessage(irc.RPL_INFO, "Originally developed for the Desert Bus for Hope charity fundraiser (http://desertbus.org)")
		user.sendMessage(irc.RPL_INFO, "")
		user.sendMessage(irc.RPL_INFO, "Developed by ElementalAlchemist <ElementAlchemist7@gmail.com>")
		user.sendMessage(irc.RPL_INFO, "Contributors:")
		user.sendMessage(irc.RPL_INFO, "   Heufneutje")
		user.sendMessage(irc.RPL_INFO, "")
		user.sendMessage(irc.RPL_INFO, "Past contributors:")
		user.sendMessage(irc.RPL_INFO, "   ekimekim")
		user.sendMessage(irc.RPL_INFO, "")
		user.sendMessage(irc.RPL_INFO, "Created and initially developed by ojii, Fugiman, and ElementalAlchemist")
		user.sendMessage(irc.RPL_ENDOFINFO, "End of /INFO list")
		return True

infoCmd = InfoCommand()