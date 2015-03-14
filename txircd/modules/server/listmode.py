from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType
from zope.interface import implements
from datetime import datetime

class ListModeSync(ModuleData):
	implements(IPlugin, IModuleData)
	
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
	
	def setModes(self, target):
		target.setModes(self.modeCache[target])
		del self.modeCache[target]

class ListModeCmd(Command):
	implements(ICommand)
	
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
					"targettime": datetime.utcfromtimestamp(int(params[1])),
					"mode": params[2],
					"param": params[3],
					"setter": params[4],
					"modetime": datetime.utcfromtimestamp(int(params[5]))
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
					"targettime": datetime.utcfromtimestamp(int(params[1])),
					"mode": params[2],
					"param": params[3],
					"setter": params[4],
					"modetime": datetime.utcfromtimestamp(int(params[5]))
				}
			except ValueError:
				return None
		return None
	
	def execute(self, server, data):
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

class EndListModeCmd(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		if params[0] not in self.ircd.channels and params[0] not in self.ircd.users:
			return None
		return {
			"target": params[0]
		}
	
	def execute(self, server, data):
		self.module.setModes(data["target"])
		return True

listModeSync = ListModeSync()