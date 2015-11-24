from twisted.plugin import IPlugin
from txircd.channel import IRCChannel
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType
from zope.interface import implements
from datetime import datetime

class FJoinCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "FJoinCommand"
	core = True
	
	def serverCommands(self):
		return [ ("FJOIN", 1, self) ]
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) < 4:
			return None
		try:
			time = datetime.utcfromtimestamp(int(params[1]))
		except ValueError:
			return None
		modes = {}
		currParam = 3
		for mode in params[2]:
			if mode == "+":
				continue
			if mode not in self.ircd.channelModeTypes or self.ircd.channelModeTypes[mode] == ModeType.Status:
				return None
			modeType = self.ircd.channelModeTypes[mode]
			if modeType in (ModeType.ParamOnUnset, ModeType.Param):
				try:
					modes[mode] = params[currParam]
				except IndexError:
					return None
				currParam += 1
			else:
				modes[mode] = None
		try:
			usersInChannel = params[currParam].split()
		except IndexError:
			return None
		if currParam + 1 < len(params):
			return None
		users = {}
		try:
			for userData in usersInChannel:
				ranks, uuid = userData.split(",")
				if uuid not in self.ircd.users:
					return None
				for rank in ranks:
					if rank not in self.ircd.channelModeTypes or self.ircd.channelModeTypes[rank] != ModeType.Status:
						return None
				users[self.ircd.users[uuid]] = ranks
		except ValueError:
			return None
		if params[0] in self.ircd.channels:
			channel = self.ircd.channels[params[0]]
		else:
			channel = IRCChannel(self.ircd, params[0])
		return {
			"channel": channel,
			"time": time,
			"modes": modes,
			"users": users
		}
	
	def execute(self, server, data):
		channel = data["channel"]
		time = data["time"]
		remoteModes = data["modes"]
		remoteStatuses = []
		for user, ranks in data["users"].iteritems():
			user.joinChannel(channel, True, True)
			for rank in ranks:
				remoteStatuses.append((user.uuid, rank))
		if time < channel.existedSince:
			modeUnsetList = []
			for mode, param in channel.modes.iteritems():
				modeType = self.ircd.channelModeTypes[mode]
				if modeType == ModeType.List:
					for paramData in param:
						modeUnsetList.append((False, mode, paramData[0]))
				else:
					modeUnsetList.append((False, mode, param))
			for user, data in channel.users.iteritems():
				for rank in data["status"]:
					modeUnsetList.append((False, rank, user.uuid))
			if modeUnsetList:
				channel.setModes(modeUnsetList, self.ircd.serverID)
			channel.existedSince = time
		if time == channel.existedSince:
			modeSetList = []
			for mode, param in remoteModes.iteritems():
				modeSetList.append((True, mode, param))
			for status in remoteStatuses:
				modeSetList.append((True, status[1], status[0]))
			if modeSetList:
				channel.setModes(modeSetList, self.ircd.serverID)
		return True

fjoinCmd = FJoinCommand()