from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType, timestampStringFromTime, timestampStringFromTimeSeconds
from zope.interface import implements
from datetime import datetime

irc.RPL_CREATIONTIME = "329"

class ModeCommand(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ModeCommand"
	core = True
	
	def actions(self):
		return [ ("modemessage-channel", 1, self.sendChannelModesToUsers),
		         ("modechanges-channel", 1, self.sendChannelModesToServers),
		         ("modemessage-user", 1, self.sendUserModesToUsers),
		         ("modechanges-user", 1, self.sendUserModesToServers),
		         ("commandpermission-MODE", 1, self.restrictUse),
		         ("buildisupport", 1, self.buildISupport) ]
	
	def userCommands(self):
		return [ ("MODE", 1, UserMode(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("MODE", 1, ServerMode(self.ircd)) ]
	
	def getOutputModes(self, modes, useUUIDs):
		addInStr = None
		modeStrList = []
		params = []
		modeLists = []
		modeLen = 0
		for modeData in modes:
			adding, mode, param, setBy, setTime = modeData
			paramLen = 0
			if param is not None:
				paramLen = len(param)
			if modeLen + paramLen + 3 > 300: # Don't let the mode output get too long
				modeLists.append(["".join(modeStrList)] + params)
				addInStr = None
				modeStrList = []
				params = []
				modeLen = 0
			if adding != addInStr:
				if adding:
					modeStrList.append("+")
				else:
					modeStrList.append("-")
				addInStr = adding
				modeLen += 1
			modeStrList.append(mode)
			modeLen += 1
			if param is not None:
				if not useUUIDs and self.ircd.channelModeTypes[mode] == ModeType.Status:
					param = self.ircd.users[param].nick
				params.append(param)
				modeLen += 1 + paramLen
		modeLists.append(["".join(modeStrList)] + params)
		return modeLists
	
	def sendChannelModesToUsers(self, users, channel, source, sourceName, modes):
		modeOuts = self.getOutputModes(modes, False)
		userSource = source in self.ircd.users
		if userSource:
			conditionalTags = {}
			self.ircd.runActionStandard("sendingusertags", self.ircd.users[source], conditionalTags)
		for modeOut in modeOuts:
			modeStr = modeOut[0]
			params = modeOut[1:]
			for user in users:
				tags = {}
				if userSource:
					tags = user.filterConditionalTags(conditionalTags)
				user.sendMessage("MODE", modeStr, *params, prefix=sourceName, to=channel.name, tags=tags)
		del users[:]
	
	def sendChannelModesToServers(self, channel, source, sourceName, modes):
		modeOuts = self.getOutputModes(modes, True)
		
		if source[:3] == self.ircd.serverID:
			fromServer = None
		else:
			fromServer = self.ircd.servers[source[:3]]
			while fromServer.nextClosest != self.ircd.serverID:
				fromServer = self.ircd.servers[fromServer.nextClosest]
		for modeOut in modeOuts:
			modeStr = modeOut[0]
			params = modeOut[1:]
			self.ircd.broadcastToServers(fromServer, "MODE", channel.name, timestampStringFromTime(channel.existedSince), modeStr, *params, prefix=source)
	
	def sendUserModesToUsers(self, users, user, source, sourceName, modes):
		modeOuts = self.getOutputModes(modes, False)
		userSource = source in self.ircd.users
		if userSource:
			conditionalTags = {}
			self.ircd.runActionStandard("sendingusertags", self.ircd.users[source], conditionalTags)
		for modeOut in modeOuts:
			modeStr = modeOut[0]
			params = modeOut[1:]
			for u in set(users):
				tags = {}
				if userSource:
					tags = user.filterConditionalTags(conditionalTags)
				u.sendMessage("MODE", modeStr, *params, prefix=sourceName, to=user.nick, tags=tags)
		del users[:]
	
	def sendUserModesToServers(self, user, source, sourceName, modes):
		if not user.isRegistered():
			return # If the user isn't registered yet, it's a remote user for whom we just received modes
		modeOuts = self.getOutputModes(modes, False)
		
		if source[:3] == self.ircd.serverID:
			fromServer = None
		else:
			fromServer = self.ircd.servers[source[:3]]
			while fromServer.nextClosest != self.ircd.serverID:
				fromServer = self.ircd.servers[fromServer.nextClosest]
		for modeOut in modeOuts:
			modeStr = modeOut[0]
			params = modeOut[1:]
			self.ircd.broadcastToServers(fromServer, "MODE", user.uuid, timestampStringFromTime(user.connectedSince), modeStr, *params, prefix=source)
	
	def restrictUse(self, user, data):
		if "channel" not in data or "modes" not in data:
			return None
		if not data["params"]:
			for mode in data["modes"]:
				if mode != "+" and mode != "-" and (mode not in self.ircd.channelModeTypes or self.ircd.channelModeTypes[mode] != ModeType.List):
					break
			else:
				return None # All the modes are list modes, and there are no parameters, so we're listing list mode parameters
		channel = data["channel"]
		if not self.ircd.runActionUntilValue("checkchannellevel", "mode", channel, user, users=[user], channels=[channel]):
			user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, "You do not have access to set channel modes")
			return False
		return None

	def buildISupport(self, data):
		data["MODES"] = self.ircd.config.get("modes_per_line", 20)
		data["MAXLIST"] = "{}:{}".format("".join(self.ircd.channelModes[0].keys()), self.ircd.config.get("channel_listmode_limit", 128))

class UserMode(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params or not params[0]:
			user.sendSingleError("ModeCmd", irc.ERR_NEEDMOREPARAMS, "MODE", "Not enough parameters")
			return None
		channel = None
		if params[0] in self.ircd.channels:
			channel = self.ircd.channels[params[0]]
		elif params[0] in self.ircd.userNicks:
			if self.ircd.userNicks[params[0]] != user:
				user.sendSingleError("ModeCmd", irc.ERR_USERSDONTMATCH, "Can't operate on modes for other users")
				return None
		else:
			user.sendSingleError("ModeCmd", irc.ERR_NOSUCHNICK, params[0], "No such nick/channel")
			return None
		if len(params) == 1:
			if channel:
				return {
					"channel": channel
				}
			return {}
		modeStr = params[1]
		modeParams = params[2:]
		if channel:
			return {
				"channel": channel,
				"modes": modeStr,
				"params": modeParams
			}
		return {
			"modes": modeStr,
			"params": modeParams
		}
	
	def affectedChannels(self, user, data):
		if "channel" in data:
			return [ data["channel"] ]
		return []
	
	def execute(self, user, data):
		if "modes" not in data:
			if "channel" in data:
				channel = data["channel"]
				user.sendMessage(irc.RPL_CHANNELMODEIS, channel.name, *(channel.modeString(user).split(" ")))
				user.sendMessage(irc.RPL_CREATIONTIME, channel.name, timestampStringFromTimeSeconds(channel.existedSince))
				return True
			user.sendMessage(irc.RPL_UMODEIS, user.modeString(user))
			return True
		if "channel" in data:
			channel = data["channel"]
			channel.setModesByUser(user, data["modes"], data["params"])
			return True
		user.setModesByUser(user, data["modes"], data["params"])
		return True

class ServerMode(Command):
	implements(ICommand)
	
	burstQueuePriority = 70
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) < 3:
			return None
		if prefix not in self.ircd.users and prefix not in self.ircd.servers:
			if prefix in self.ircd.recentlyQuitUsers or prefix in self.ircd.recentlyQuitServers:
				return {
					"lostsource": True
				}
			return None # It's safe to say other servers shouldn't be sending modes sourced from us. That's our job! (That's why we don't test for that.)
		if params[0] not in self.ircd.users and params[0] not in self.ircd.channels:
			if params[0] in self.ircd.recentlyQuitUsers or params[0] in self.ircd.recentlyDestroyedChannels:
				return {
					"losttarget": True
				}
			return None
		
		time = None
		try:
			time = datetime.utcfromtimestamp(float(params[1]))
		except (TypeError, ValueError):
			return None
		
		modes = params[2]
		parameters = params[3:]
		parsedModes = []
		modeTypes = {}
		if params[0] in self.ircd.channels:
			modeTypes = self.ircd.channelModeTypes
		else:
			modeTypes = self.ircd.userModeTypes
		adding = True
		for mode in modes:
			if mode == "+":
				adding = True
			elif mode == "-":
				adding = False
			else:
				if mode not in modeTypes:
					return None # Uh oh, a desync!
				modeType = modeTypes[mode]
				parameter = None
				if modeType in (ModeType.Status, ModeType.List, ModeType.ParamOnUnset) or (adding and modeType == ModeType.Param):
					parameter = parameters.pop(0)
				parsedModes.append((adding, mode, parameter))
		
		return {
			"source": prefix,
			"target": params[0],
			"time": time,
			"modes": parsedModes
		}
	
	def execute(self, server, data):
		if "lostsource" in data or "losttarget" in data:
			return True
		source = data["source"]
		target = data["target"]
		targetTime = data["time"]
		if target in self.ircd.channels:
			channel = self.ircd.channels[target]
			if targetTime > channel.existedSince:
				return True
			if targetTime < channel.existedSince:
				channel.setCreationTime(targetTime)
			# We'll need to transform the user parameters of status modes before we're done here
			channel.setModes(data["modes"], source)
			return True
		user = self.ircd.users[target]
		if targetTime > user.connectedSince:
			return True
		if targetTime < user.connectedSince:
			modeUnsetList = []
			for mode, param in user.modes.iteritems():
				if self.ircd.userModeTypes[mode] == ModeType.List:
					for paramData in param:
						modeUnsetList.append((False, mode, paramData[0]))
				else:
					modeUnsetList.append((False, mode, param))
			if modeUnsetList:
				user.setModes(modeUnsetList, source)
		user.setModes(data["modes"], source)
		return True

modeCommand = ModeCommand()