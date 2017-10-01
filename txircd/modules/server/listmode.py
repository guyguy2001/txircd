from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType
from zope.interface import implementer
from datetime import datetime

@implementer(IPlugin, IModuleData)
class ListModeSync(ModuleData):
	name = "ListModeSync"
	core = True
	modeCache = {}
	
	def serverCommands(self):
		return [ ("LISTMODE", 1, ListModeCmd(self)),
		         ("ENDLISTMODE", 1, EndListModeCmd(self)) ]
	
	def addListMode(self, target, modeData):
		if target not in self.modeCache:
			self.modeCache[target] = []
		self.modeCache[target].append(modeData)
	
	def setModes(self, target, fromServer):
		if target in self.modeCache:
			target.setModes(self.modeCache[target], fromServer.serverID)
			del self.modeCache[target]
	
	def clearUser(self, userUUID):
		for target in self.modeCache.keys():
			try:
				if target.uuid == userUUID:
					del self.modeCache[target]
					return
			except AttributeError:
				pass
	
	def clearChannel(self, channelName):
		for target in self.modeCache.keys():
			try:
				if target.name == channelName:
					del self.modeCache[target]
					return
			except AttributeError:
				pass

@implementer(ICommand)
class ListModeCmd(Command):
	burstQueuePriority = 70
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 6:
			return None
		if params[0] in self.ircd.channels:
			if params[2] not in self.ircd.channelModeTypes:
				return None
			if self.ircd.channelModeTypes[params[2]] != ModeType.List:
				return None
			try:
				return {
					"target": self.ircd.channels[params[0]],
					"targettime": datetime.utcfromtimestamp(float(params[1])),
					"mode": params[2],
					"param": params[3],
					"setter": params[4],
					"modetime": datetime.utcfromtimestamp(float(params[5]))
				}
			except ValueError:
				return None
		if params[0] in self.ircd.users:
			if params[2] not in self.ircd.userModeTypes:
				return None
			if self.ircd.userModeTypes[params[2]] != ModeType.List:
				return None
			try:
				return {
					"target": self.ircd.users[params[0]],
					"targettime": datetime.utcfromtimestamp(float(params[1])),
					"mode": params[2],
					"param": params[3],
					"setter": params[4],
					"modetime": datetime.utcfromtimestamp(float(params[5]))
				}
			except ValueError:
				return None
		if params[0] in self.ircd.recentlyQuitUsers or params[0] in self.ircd.recentlyDestroyedChannels:
			return {
				"losttarget": True
			}
		return None
	
	def execute(self, server, data):
		if "losttarget" in data:
			return True
		targetTime = data["targettime"]
		target = data["target"]
		mode = data["mode"]
		param = data["param"]
		try: # Check channel timestamp
			if targetTime > target.existedSince:
				return True # We handled it such that it's not a desync
		except AttributeError: # Check user timestamp
			if targetTime > target.connectedSince:
				return True
		self.module.addListMode(target, (True, mode, param, data["setter"], data["modetime"]))
		return True

@implementer(ICommand)
class EndListModeCmd(Command):
	burstQueuePriority = 70
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if params[0] in self.ircd.channels:
			return {
				"target": self.ircd.channels[params[0]]
			}
		if params[0] in self.ircd.users:
			return {
				"target": self.ircd.users[params[0]]
			}
		if params[0] in self.ircd.recentlyQuitUsers:
			return {
				"lostuser": params[0]
			}
		if params[0] in self.ircd.recentlyDestroyedChannels:
			return {
				"lostchannel": params[0]
			}
		return None
	
	def execute(self, server, data):
		if "lostuser" in data:
			self.module.clearUser(data["lostuser"])
		elif "lostchannel" in data:
			self.module.clearChannel(data["lostchannel"])
		else:
			self.module.setModes(data["target"], server)
		return True

listModeSync = ListModeSync()