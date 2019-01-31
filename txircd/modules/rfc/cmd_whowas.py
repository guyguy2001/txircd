from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import durationToSeconds, ipAddressToShow, ircLower, now
from zope.interface import implementer
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

irc.RPL_WHOWASIP = "379"

@implementer(IPlugin, IModuleData, ICommand)
class WhowasCommand(ModuleData, Command):
	name = "WhowasCommand"
	core = True
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("quit", 10, self.addUserToWhowas),
		         ("remotequit", 10, self.addUserToWhowas),
		         ("localquit", 10, self.addUserToWhowas) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("WHOWAS", 1, self) ]
	
	def load(self) -> None:
		if "whowas" not in self.ircd.storage:
			self.ircd.storage["whowas"] = {}

	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "whowas_duration" in config and not isinstance(config["whowas_duration"], str) and not isinstance(config["whowas_duration"], int):
			raise ConfigValidationError("whowas_duration", "value must be an integer or a duration string")
		if "whowas_max_entries" in config and (not isinstance(config["whowas_max_entries"], int) or config["whowas_max_entries"] < 0):
			raise  ConfigValidationError("whowas_max_entries", "invalid number")
	
	def removeOldEntries(self, whowasEntries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
		expireDuration = durationToSeconds(self.ircd.config.get("whowas_duration", "1d"))
		maxCount = self.ircd.config.get("whowas_max_entries", 10)
		while whowasEntries and len(whowasEntries) > maxCount:
			whowasEntries.pop(0)
		expireDifference = timedelta(seconds=expireDuration)
		expireTime = now() - expireDifference
		while whowasEntries and whowasEntries[0]["when"] < expireTime:
			whowasEntries.pop(0)
		return whowasEntries
	
	def addUserToWhowas(self, user: "IRCUser", reason: str, fromServer: "IRCServer" = None) -> None:
		if not user.isRegistered():
			# user never registered a nick, so no whowas entry to add
			return
		lowerNick = ircLower(user.nick)
		allWhowas = self.ircd.storage["whowas"]
		if lowerNick in allWhowas:
			whowasEntries = allWhowas[lowerNick]
		else:
			whowasEntries = []
		serverName = self.ircd.name
		if user.uuid[:3] != self.ircd.serverID:
			serverName = self.ircd.servers[user.uuid[:3]].name
		whowasEntries.append({
			"nick": user.nick,
			"ident": user.ident,
			"host": user.host(),
			"realhost": user.realHost,
			"ip": ipAddressToShow(user.ip),
			"gecos": user.gecos,
			"server": serverName,
			"when": now()
		})
		whowasEntries = self.removeOldEntries(whowasEntries)
		if whowasEntries:
			allWhowas[lowerNick] = whowasEntries
		elif lowerNick in allWhowas:
			del allWhowas[lowerNick]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("WhowasCmd", irc.ERR_NEEDMOREPARAMS, "WHOWAS", "Not enough parameters")
			return None
		lowerParam = ircLower(params[0])
		if lowerParam not in self.ircd.storage["whowas"]:
			user.sendSingleError("WhowasNick", irc.ERR_WASNOSUCHNICK, params[0], "There was no such nickname")
			return None
		return {
			"nick": lowerParam,
			"param": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		nick = data["nick"]
		allWhowas = self.ircd.storage["whowas"]
		whowasEntries = allWhowas[nick]
		whowasEntries = self.removeOldEntries(whowasEntries)
		if not whowasEntries:
			del allWhowas[nick]
			self.ircd.storage["whowas"] = allWhowas
			user.sendMessage(irc.ERR_WASNOSUCHNICK, data["param"], "There was no such nickname")
			return True
		allWhowas[nick] = whowasEntries # Save back to the list excluding the removed entries
		self.ircd.storage["whowas"] = allWhowas
		for entry in whowasEntries:
			entryNick = entry["nick"]
			user.sendMessage(irc.RPL_WHOWASUSER, entryNick, entry["ident"], entry["host"], "*", entry["gecos"])
			if self.ircd.runActionUntilValue("userhasoperpermission", user, "whowas-host", users=[user]):
				user.sendMessage(irc.RPL_WHOWASIP, entryNick, "was connecting from {}@{} {}".format(entry["ident"], entry["realhost"], entry["ip"]))
			user.sendMessage(irc.RPL_WHOISSERVER, entryNick, entry["server"], str(entry["when"]))
		user.sendMessage(irc.RPL_ENDOFWHOWAS, nick, "End of WHOWAS")
		return True

whowasCmd = WhowasCommand()