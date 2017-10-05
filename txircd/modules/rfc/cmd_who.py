from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ircLower
from zope.interface import implementer
from fnmatch import fnmatchcase
from typing import Any, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class WhoCommand(ModuleData, Command):
	name = "WhoCommand"
	core = True
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("WHO", 1, self) ]
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			return {
				"mask": "*"
			}
		if len(params) > 1 and params[1] == "o":
			return {
				"mask": params[0],
				"opersonly": True
			}
		return {
			"mask": params[0]
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		matchingUsers = []
		channel = None
		mask = data["mask"]
		if mask in ("0", "*"):
			for targetUser in self.ircd.users.values():
				if not targetUser.isRegistered():
					continue
				if not set(user.channels).intersection(targetUser.channels) and self.ircd.runActionUntilValue("showuser", user, targetUser, users=[user, targetUser]) is not False:
					matchingUsers.append(targetUser)
		elif mask in self.ircd.channels:
			channel = self.ircd.channels[data["mask"]]
			for targetUser in channel.users.keys():
				if self.ircd.runActionUntilValue("showchanneluser", channel, user, targetUser, users=[user, targetUser], channels=[channel]) is not False:
					matchingUsers.append(targetUser)
		else:
			for targetUser in self.ircd.users.values():
				if not targetUser.isRegistered():
					continue # We should exclude all unregistered users from this search
				if self.ircd.runActionUntilValue("showuser", user, targetUser, users=[user, targetUser]) is False:
					continue
				lowerMask = ircLower(mask)
				serverName = self.ircd.name if targetUser.uuid[:3] == self.ircd.serverID else self.ircd.servers[targetUser.uuid[:3]].name
				if fnmatchcase(ircLower(targetUser.host()), lowerMask) or fnmatchcase(ircLower(targetUser.gecos), lowerMask) or fnmatchcase(ircLower(serverName), lowerMask) or fnmatchcase(ircLower(targetUser.nick), lowerMask):
					matchingUsers.append(targetUser)
		if "opersonly" in data:
			allMatches = matchingUsers
			matchingUsers = []
			for targetUser in allMatches:
				if self.ircd.runActionUntilValue("userhasoperpermission", targetUser, "", users=[targetUser]):
					matchingUsers.append(targetUser)
		for targetUser in matchingUsers:
			server = self.ircd if targetUser.uuid[:3] == self.ircd.serverID else self.ircd.servers[targetUser.uuid[:3]]
			serverName = server.name
			isOper = self.ircd.runActionUntilValue("userhasoperpermission", targetUser, "", users=[targetUser])
			isAway = targetUser.metadataKeyExists("away")
			status = self.ircd.runActionUntilValue("channelstatuses", channel, targetUser, user, users=[targetUser, user], channels=[channel]) if channel else ""
			hopcount = 0
			if user.uuid[:3] != self.ircd.serverID:
				countingServer = server
				hopcount = 1
				while countingServer.nextClosest != self.ircd.serverID:
					countingServer = self.ircd.servers[countingServer.nextClosest]
					hopcount += 1
			user.sendMessage(irc.RPL_WHOREPLY, mask, targetUser.ident, targetUser.host(), serverName, targetUser.nick, "{}{}{}".format("G" if isAway else "H", "*" if isOper else "", status), "{} {}".format(hopcount, targetUser.gecos))
		user.sendMessage(irc.RPL_ENDOFWHO, mask, "End of /WHO list")
		return True

whoCommand = WhoCommand()