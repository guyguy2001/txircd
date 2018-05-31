from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.user import RemoteUser
from txircd.utils import ipAddressToShow, ModeType, now, timestampStringFromTime
from zope.interface import implementer
from datetime import datetime
from ipaddress import ip_address
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData, ICommand)
class ServerUID(ModuleData, Command):
	name = "ServerUID"
	core = True
	burstQueuePriority = 90
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("welcome", 500, self.broadcastUID) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("UID", 1, self) ]
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 10:
			return None
		uuid, signonTS, nick, realHost, displayHost, hostType, ident, ip, nickTS, connectionFlags = params[:10]
		try:
			connectTime = datetime.utcfromtimestamp(float(signonTS))
			nickTime = datetime.utcfromtimestamp(float(nickTS))
		except ValueError:
			return None
		currParam = 11
		modes = {}
		for mode in params[10]:
			if mode == "+":
				continue
			try:
				modeType = self.ircd.userModeTypes[mode]
			except KeyError:
				return None # There's a mode that's NOT REAL so get out of here
			param = None
			if modeType in (ModeType.List, ModeType.ParamOnUnset, ModeType.Param):
				param = params[currParam]
				currParam += 1
				if not param or " " in param:
					return None
			if modeType == ModeType.List:
				if mode not in modes:
					modes[mode] = []
				modes[mode].append(param)
			else:
				modes[mode] = param
		gecos = params[currParam]
		return {
			"uuid": uuid,
			"connecttime": connectTime,
			"nick": nick,
			"ident": ident,
			"host": realHost,
			"displayhost": displayHost,
			"hosttype": hostType,
			"ip": ip,
			"gecos": gecos,
			"nicktime": nickTime,
			"connflags": connectionFlags,
			"modes": modes
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		connectTime = data["connecttime"]
		nickTime = data["nicktime"]
		newUser = RemoteUser(self.ircd, ip_address(data["ip"]), data["uuid"], data["host"])
		newUser.changeHost(data["hosttype"], data["displayhost"], True)
		newUser.changeIdent(data["ident"], server)
		newUser.changeGecos(data["gecos"], True)
		newUser.connectedSince = connectTime
		newUser.nickSince = nickTime
		newUser.idleSince = now()
		if data["nick"] in self.ircd.userNicks: # Handle nick collisions
			otherUser = self.ircd.userNicks[data["nick"]]
			if otherUser.localOnly:
				changeOK = self.ircd.runActionUntilValue("localnickcollision", otherUser, newUser, server, users=[otherUser, newUser])
				if changeOK is None:
					return None
			sameUser = ("{}@{}".format(otherUser.ident, otherUser.ip.compressed) == "{}@{}".format(newUser.ident, newUser.ip.compressed))
			if sameUser and newUser.nickSince < otherUser.nickSince: # If the user@ip is the same, the newer nickname should win
				newUser.changeNick(newUser.uuid, server)
			elif sameUser and otherUser.nickSince < newUser.nickSince:
				otherUser.changeNick(otherUser.uuid, server)
			elif newUser.nickSince < otherUser.nickSince: # Otherwise, the older nickname should win
				otherUser.changeNick(otherUser.uuid, server)
			elif otherUser.nickSince < newUser.nickSince:
				newUser.changeNick(newUser.uuid, server)
			else: # If the nickname times are the same, fall back on connection times, with the same hierarchy as before
				if sameUser and newUser.connectedSince < otherUser.connectedSince:
					newUser.changeNick(newUser.uuid, server)
				elif sameUser and otherUser.connectedSince < newUser.connectedSince:
					otherUser.changeNick(otherUser.uuid, server)
				elif newUser.connectedSince < otherUser.connectedSince:
					otherUser.changeNick(otherUser.uuid, server)
				elif otherUser.connectedSince < newUser.connectedSince:
					newUser.changeNick(newUser.uuid, server)
				else: # As a final fallback, change both nicknames
					otherUser.changeNick(otherUser.uuid, server)
					newUser.changeNick(newUser.uuid, server)
		if newUser.nick is None: # wasn't set by above logic
			newUser.changeNick(data["nick"], server)
		modeList = []
		for mode, param in data["modes"].items():
			modeType = self.ircd.userModeTypes[mode]
			if modeType == ModeType.List:
				for paramData in param:
					modeList.append((True, mode, paramData))
			else:
				modeList.append((True, mode, param))
		connectionFlags = data["connflags"]
		if connectionFlags == "S":
			newUser.secureConnection = True
		newUser.setModes(modeList, server.serverID)
		newUser.register("connection", True)
		newUser.register("USER", True)
		newUser.register("NICK", True)
		connectTimestamp = timestampStringFromTime(connectTime)
		nickTimestamp = timestampStringFromTime(nickTime)
		uidParams = [newUser.uuid, connectTimestamp, newUser.nick, newUser.realHost, newUser.host(), newUser.currentHostType(), newUser.ident, ipAddressToShow(newUser.ip), nickTimestamp, connectionFlags]
		uidParams.extend(newUser.modeString(None).split(" "))
		uidParams.append(newUser.gecos)
		self.ircd.broadcastToServers(server, "UID", *uidParams, prefix=self.ircd.serverID)
		return True
	
	def broadcastUID(self, user: "IRCUser") -> None:
		uidParams = [user.uuid, timestampStringFromTime(user.connectedSince), user.nick, user.realHost, user.host(), user.currentHostType(), user.ident, ipAddressToShow(user.ip), timestampStringFromTime(user.nickSince), "S" if user.secureConnection else "*"]
		uidParams.extend(user.modeString(None).split(" "))
		uidParams.append(user.gecos)
		self.ircd.broadcastToServers(None, "UID", *uidParams, prefix=self.ircd.serverID)

serverUID = ServerUID()