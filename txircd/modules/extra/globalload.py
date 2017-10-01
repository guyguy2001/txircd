from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.ircd import ModuleLoadError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer

@implementer(IPlugin, IModuleData)
class GlobalLoad(ModuleData):
	name = "GlobalLoad"
	
	def actions(self):
		return [ ("commandpermission-GLOADMODULE", 1, self.restrictGLoad),
		         ("commandpermission-GUNLOADMODULE", 1, self.restrictGUnload),
		         ("commandpermission-GRELOADMODULE", 1, self.restrictGReload) ]
	
	def userCommands(self):
		return [ ("GLOADMODULE", 1, UserLoad(self.ircd)),
		         ("GUNLOADMODULE", 1, UserUnload(self.ircd)),
		         ("GRELOADMODULE", 1, UserReload(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("LOADMODULE", 1, ServerLoad(self.ircd)),
		         ("UNLOADMODULE", 1, ServerUnload(self.ircd)),
		         ("RELOADMODULE", 1, ServerReload(self.ircd)) ]
	
	def restrictGLoad(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-gloadmodule", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def restrictGUnload(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-gunloadmodule", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def restrictGReload(self, user, data):
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-greloadmodule", users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None

@implementer(ICommand)
class UserLoad(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendMessage(irc.ERR_NEEDMOREPARAMS, "GLOADMODULE", "Not enough parameters")
			return None
		return {
			"module": params[0]
		}
	
	def execute(self, user, data):
		moduleName = data["module"]
		if moduleName in self.ircd.loadedModules:
			user.sendMessage(irc.ERR_CANTLOADMODULE, moduleName, "Module is already loaded")
		else:
			try:
				self.ircd.loadModule(moduleName)
				if moduleName in self.ircd.loadedModules:
					user.sendMessage(irc.RPL_LOADEDMODULE, moduleName, "Module successfully loaded")
					self.ircd.broadcastToServers(None, "LOADMODULE", moduleName, prefix=user.uuid)
				else:
					user.sendMessage(irc.ERR_CANTLOADMODULE, moduleName, "No such module")
			except ModuleLoadError as e:
				user.sendMessage(irc.ERR_CANTLOADMODULE, moduleName, e.message)
		return True

@implementer(ICommand)
class UserUnload(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendMessage(irc.ERR_NEEDMOREPARAMS, "GUNLOADMODULE", "Not enough parameters")
			return None
		return {
			"module": params[0]
		}
	
	def execute(self, user, data):
		moduleName = data["module"]
		if moduleName not in self.ircd.loadedModules:
			user.sendMessage(irc.ERR_CANTUNLOADMODULE, moduleName, "No such module")
		else:
			try:
				self.ircd.unloadModule(moduleName)
				user.sendMessage(irc.RPL_UNLOADEDMODULE, moduleName, "Module successfully unloaded")
				self.ircd.broadcastToServers(None, "UNLOADMODULE", moduleName, prefix=user.uuid)
			except ValueError as e:
				user.sendMessage(irc.ERR_CANTUNLOADMODULE, moduleName, e.message)
		return True

@implementer(ICommand)
class UserReload(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendMessage(irc.ERR_NEEDMOREPARAMS, "GRELOADMODULE", "Not enough parameters")
			return None
		return {
			"module": params[0]
		}
	
	def execute(self, user, data):
		moduleName = data["module"]
		if moduleName not in self.ircd.loadedModules:
			user.sendMessage(irc.ERR_CANTUNLOADMODULE, moduleName, "No such module")
		else:
			try:
				self.ircd.reloadModule(moduleName)
				user.sendMessage(irc.RPL_LOADEDMODULE, moduleName, "Module successfully reloaded")
				self.ircd.broadcastToServers(None, "RELOADMODULE", moduleName, prefix=user.uuid)
			except ModuleLoadError as e:
				user.sendMessage(irc.ERR_CANTUNLOADMODULE, moduleName, "{}; module is now unloaded".format(e.message))
		return True

@implementer(ICommand)
class ServerLoad(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		return {
			"from": prefix,
			"module": params[0]
		}
	
	def execute(self, server, data):
		fromPrefix = data["from"]
		moduleName = data["module"]
		try:
			self.ircd.loadModule(moduleName)
		except ModuleLoadError:
			return None
		if moduleName not in self.ircd.loadedModules: # We want to log a message, but this shouldn't break the servers
			self.ircd.log.warn("Tried to globally load nonexistent module {module}", module=moduleName)
		self.ircd.broadcastToServers(server, "LOADMODULE", moduleName, prefix=fromPrefix)
		return True

@implementer(ICommand)
class ServerUnload(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		return {
			"from": prefix,
			"module": params[0]
		}
	
	def execute(self, server, data):
		fromPrefix = data["from"]
		moduleName = data["module"]
		try:
			self.ircd.unloadModule(moduleName)
		except ValueError:
			return None
		self.ircd.broadcastToServers(server, "UNLOADMODULE", moduleName, prefix=fromPrefix)
		return True

@implementer(ICommand)
class ServerReload(Command):
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 1:
			return None
		return {
			"from": prefix,
			"module": params[0]
		}
	
	def execute(self, server, data):
		fromPrefix = data["from"]
		moduleName = data["module"]
		try:
			self.ircd.reloadModule(moduleName)
		except ModuleLoadError:
			return None
		self.ircd.broadcastToServers(server, "RELOADMODULE", moduleName, prefix=fromPrefix)
		return True

globalLoad = GlobalLoad()