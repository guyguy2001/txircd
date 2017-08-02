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
	burstQueuePriority = 80
	
	def __init__(self):
		self.serverBurstData = None
	
	def actions(self):
		return [ ("startburstcommand", 10, self.prepareJoinBurst),
		         ("endburstcommand", 10, self.completeJoinBurst) ]
	
	def serverCommands(self):
		return [ ("FJOIN", 1, self) ]
	
	def prepareJoinBurst(self, server, command):
		if command != "FJOIN":
			return
		self.serverBurstData = {}
	
	def completeJoinBurst(self, server, command):
		if command != "FJOIN":
			return
		openBatchUsers = set()
		channelStatusesToSet = {}
		joinsToComplete = []
		closeBurstServerName = self.ircd.servers[server.nextClosest].name if server.nextClosest in self.ircd.servers else self.ircd.name
		farBurstServerName = server.name
		
		# First, handle channel timestamps
		for channel, channelData in self.serverBurstData.iteritems():
			channelTime = channelData["time"]
			if channelTime < channel.existedSince:
				channel.setCreationTime(channelTime, server)
		
		# Next, start processing all the joins. We don't finish this here because we want to send only one netjoin batch,
		# so we accumulate all the joins, then flush the batch, then complete all the joins and do modes/other post-processing.
		for channel, channelData in self.serverBurstData.iteritems():
			for user, ranks in channelData["users"].iteritems():
				joinChannelData = user.joinChannelNoAnnounceIncomplete(channel, False, server)
				if not joinChannelData:
					continue
				joinNotifyUsers = user.joinChannelNoAnnounceNotifyUsers(joinChannelData)
				for notifyUser in joinNotifyUsers:
					if notifyUser not in openBatchUsers:
						notifyUser.createMessageBatch("netjoin", "netjoin", (closeBurstServerName, farBurstServerName))
						openBatchUsers.add(notifyUser)
				self.ircd.runActionProcessing("joinmessage", joinNotifyUsers, channel, user, "netjoin", users=joinNotifyUsers, channels=[channel])
				joinsToComplete.append((user, joinChannelData))
				if channel not in channelStatusesToSet:
					channelStatusesToSet[channel] = []
				for rank in ranks:
					channelStatusesToSet[channel].append((True, rank, user.uuid))
		# Flush batches
		for notifyUser in openBatchUsers:
			notifyUser.sendBatch("netjoin")
		# Complete joining
		for user, joinChannelData in joinsToComplete:
			user.joinChannelNoAnnounceFinish(joinChannelData)
		# Manage modes
		for channel, channelData in self.serverBurstData.iteritems():
			channelSetModes = []
			time = channelData["time"]
			if time == channel.existedSince:
				for mode, param in channelData["modes"].iteritems():
					channelSetModes.append((True, mode, param))
				if channel in channelStatusesToSet:
					channelSetModes.extend(channelStatusesToSet[channel])
			if channelSetModes:
				channel.setModes(channelSetModes, self.ircd.serverID)
	
	def parseParams(self, server, params, prefix, tags):
		if self.serverBurstData is None:
			return None
		if len(params) < 4:
			return None
		try:
			time = datetime.utcfromtimestamp(float(params[1]))
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
				ranks, uuid = userData.split(",", 1)
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
		if channel not in self.serverBurstData:
			self.serverBurstData[channel] = { "time": time, "modes": remoteModes, "users": data["users"] }
		else:
			newUsers = self.serverBurstData[channel]["users"]
			newUsers.update(data["users"])
			self.serverBurstData[channel] = { "time": time, "modes": remoteModes, "users": newUsers }
		return True

fjoinCmd = FJoinCommand()