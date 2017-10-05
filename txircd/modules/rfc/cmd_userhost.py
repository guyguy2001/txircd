from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class UserhostCommand(ModuleData, Command):
	name = "UserhostCommand"
	core = True
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("USERHOST", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("UserhostParams", irc.ERR_NEEDMOREPARAMS, "USERHOST", "Not enough parameters")
			return None
		return {
			"nicks": params[:5]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		userHosts = []
		for nick in data["nicks"]:
			if nick not in self.ircd.userNicks:
				continue
			targetUser = self.ircd.userNicks[nick]
			output = targetUser.nick
			if self.ircd.runActionUntilValue("userhasoperpermission", targetUser, "", users=[targetUser]):
				output += "*"
			output += "="
			if targetUser.metadataKeyExists("away"):
				output += "-"
			else:
				output += "+"
			output += "{}@{}".format(targetUser.ident, targetUser.host())
			userHosts.append(output)
		user.sendMessage(irc.RPL_USERHOST, " ".join(userHosts))
		return True

userhostCmd = UserhostCommand()