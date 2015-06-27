from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.user import RemoteUser
from txircd.utils import ModeType, now, timestamp
from zope.interface import implements
from datetime import datetime

class ServerUID(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ServerUID"
	core = True
	
	def actions(self):
		return [ ("welcome", 500, self.broadcastUID) ]
	
	def serverCommands(self):
		return [ ("UID", 1, self) ]
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) < 9:
			return None
		uuid, signonTS, nick, realHost, displayHost, hostType, ident, ip, nickTS = params[:9]
		try:
			connectTime = datetime.utcfromtimestamp(int(signonTS))
			nickTime = datetime.utcfromtimestamp(int(nickTS))
		except ValueError:
			return None
		currParam = 10
		modes = {}
		for mode in params[9]:
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
			"modes": modes
		}
	
	def execute(self, server, data):
		connectTime = data["connecttime"]
		nickTime = data["nicktime"]
		newUser = RemoteUser(self.ircd, data["ip"], data["uuid"], data["host"])
		newUser.changeHost(data["hosttype"], data["displayhost"], True)
		newUser.changeIdent(data["ident"], server)
		newUser.changeGecos(data["gecos"], True)
		newUser.connectedSince = connectTime
		newUser.nickSince = nickTime
		newUser.idleSince = now()
		if data["nick"] in self.ircd.userNicks: # Handle nick collisions
			otherUser = self.ircd.users[self.ircd.userNicks[data["nick"]]]
			if otherUser.localOnly:
				changeOK = self.ircd.runActionUntilValue("localnickcollision", otherUser, newUser, server, users=[otherUser, newUser])
				if changeOK is None:
					return None
			sameUser = ("{}@{}".format(otherUser.ident, otherUser.ip) == "{}@{}".format(newUser.ident, newUser.ip))
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
		for mode, param in data["modes"].iteritems():
			modeType = self.ircd.userModeTypes[mode]
			if modeType == ModeType.List:
				for paramData in param:
					modeList.append((True, mode, paramData))
			else:
				modeList.append((True, mode, param))
		newUser.setModes(modeList, server.serverID)
		newUser.register("connection", True)
		newUser.register("USER", True)
		newUser.register("NICK", True)
		connectTimestamp = str(timestamp(connectTime))
		nickTimestamp = str(timestamp(nickTime))
		modeString = newUser.modeString(None)
		self.ircd.broadcastToServers(server, "UID", newUser.uuid, connectTimestamp, newUser.nick, newUser.realHost, newUser.host(), newUser.currentHostType(), newUser.ident, newUser.ip, nickTimestamp, modeString, newUser.gecos, prefix=self.ircd.serverID)
		return True
	
	def broadcastUID(self, user):
		self.ircd.broadcastToServers(None, "UID", user.uuid, str(timestamp(user.connectedSince)), user.nick, user.realHost, user.host(), user.currentHostType(), user.ident, user.ip, str(timestamp(user.nickSince)), user.modeString(None), user.gecos, prefix=self.ircd.serverID)

serverUID = ServerUID()