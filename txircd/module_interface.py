from zope.interface import Attribute, Interface

class IModuleData(Interface):
	name = Attribute("The module name.")
	requiredOnAllServers = Attribute("""
		Whether the module must be loaded on all servers in order to function properly.
		This is determined automatically in many cases, such as if the module provides modes
		or server commands.  If the IRCd determines that the module doesn't need to be loaded
		on all servers but it actually does, it will check this value.
		""")
	multipleModulesForServers = Attribute("""
		If the functionality presented by this module to other servers is also represented
		by other modules and each module will only be loaded on some of the servers, this flag
		will prevent the autocalculation from determining that your module must be loaded on
		all servers.
		""")
	core = Attribute("Always false for custom modules.")
	
	def hookIRCd(ircd):
		"""
		Provides the IRCd instance to save and use later.
		"""
	
	def channelModes():
		"""
		Returns the channel modes provided by the module.  The modes are returned as
		a list of tuples:
		[ (letter, type, object, rank, symbol) ]
		The letter is the letter of the mode.
		The type is a mode type, one of ModeType.List, ModeType.ParamOnUnset, ModeType.Param,
			ModeType.NoParam, and ModeType.Status.  (ModeType is in txircd.utils.)
		The object is an instance of the class that implements the mode.
		The rank is a numeric value only relevant for ModeType.Status modes.  Higher numbers
			indicate a higher channel rank.  The default chanop mode +o has a rank of 100, and
			the default voice mode +v has a rank of 10.
		The symbol is a single character, also only relevant for ModeType.Status modes.
		"""
	
	def userModes():
		"""
		Returns the user modes provided by the module.  The modes are returned as a list
		of tuples:
		[ (letter, type, object) ]
		The letter is the letter of the mode.
		The type is a mode type, one of ModeType.List, ModeType.ParamOnUnset, ModeType.Param,
			and ModeType.NoParam.  (ModeType is in txircd.utils.)
		The object is an instance of the class that implements the mode.
		"""
	
	def actions():
		"""
		Returns the actions this module handles.  The actions are returned as a list
		of tuples:
		[ (type, priority, function) ]
		The name is the name of the action as a string.
		The priority is a number.  Higher priorities will be executed first.  This may
		not be important for all actions; if you think priority doesn't matter for the
		action you're implementing, a typical "normal priority" is 10.
		The function is a reference to the function which handles the action in your module.
		"""
	
	def userCommands():
		"""
		Returns commands supported by this module.  Commands are returned as a list of tuples:
		[ (name, priority, object) ]
		The name is the command.
		The priority is a number indicating where in priority order a module should handle
			the command.  It is recommended that the default implementation of a commmand have
			a priority of 1; other modules may then extend the default implementation by
			providing higher numbers.
		The object is an instance of the class that implements the command.
		"""
	
	def serverCommands():
		"""
		Returns server commands supported by this module.  Server commands are returned as
		a list of tuples:
		[ (name, priority, object) ]
		The name is the command.
		The priority is a number indicating where in priority order a module should handle
			the command.  It is recommended that the default implementation of a command have
			a priority of 1; other modules may then extend the default implementation by
			providing higher numbers.
		The object is an instance of the class that implements the command.
		"""
	
	def load():
		"""
		Called when the module is successfully loaded.
		"""
	
	def rehash():
		"""
		Called when the server is rehashed.  Indicates that new configuration values are loaded
		and that any changes should be acted upon.
		"""
	
	def unload():
		"""
		Called when the module is being unloaded for any reason, including to be reloaded.
		Should do basic cleanup.
		"""
	
	def fullUnload():
		"""
		Called when the module is being fully unloaded with no intention to reload.
		Should do full cleanup of any data this module uses, including unsetting of modes
		handled by this module.
		"""

class ModuleData(object):
	requiredOnAllServers = False
	multipleModulesForServers = False
	core = False
	
	def hookIRCd(self, ircd):
		self.ircd = ircd
	
	def channelModes(self):
		return []
	
	def userModes(self):
		return []
	
	def actions(self):
		return []
	
	def userCommands(self):
		return []
	
	def serverCommands(self):
		return []
	
	def load(self):
		pass
	
	def rehash(self):
		pass
	
	def unload(self):
		pass
	
	def fullUnload(self):
		pass


class ICommand(Interface):
	resetsIdleTime = Attribute("Whether this command resets the user's idle time.")
	forRegistered = Attribute("""
		Whether this command should be triggered for users only after they've registered.
		True to only activate for registered users.
		False to only activate for unregistered users.
		None to be agnostic about the whole thing.
		This flag is ignored for servers, except that non-True commands will be executed
		immediately upon receiving instead of going on the burst queue during bursting.
		""")
	
	def parseParams(source, params, prefix, tags):
		"""
		Parses the parameters to the command.  Returns a dictionary of data, or None if
		the parameters cannot be properly parsed.
		"""
	
	def affectedUsers(source, data):
		"""
		Determines which users are affected given parsed command data to determine which
		action functions to call.
		Returns a list of users (or an empty list for no users).
		The user who issued the command is automatically added to this list if that user
		is not already in it.
		"""
	
	def affectedChannels(source, data):
		"""
		Determines which channels are affected given parsed command data to determine
		which action functions to call.
		Returns a list of channels (or an empty list for no channels).
		"""
	
	def execute(source, data):
		"""
		Performs the command action.
		Returns True if successfully handled; otherwise defers to the next handler in the chain
		"""

class Command(object):
	resetsIdleTime = True
	forRegistered = True
	
	def parseParams(self, source, params, prefix, tags):
		return None
	
	def affectedUsers(self, source, data):
		return []
	
	def affectedChannels(self, source, data):
		return []
	
	def execute(self, source, data):
		pass


class IMode(Interface):
	affectedActions = Attribute("""
		A dict of action types for which to trigger the mode handler. Each action type in
		the dict maps to a priority.
		""")
	
	def checkSet(target, param):
		"""
		Checks whether the mode can be set.  Returns a list of parameters, or None if the mode cannot be set.
		For non-list modes, return a list of one item.
		For non-parameter modes, return an empty list.
		"""
	
	def checkUnset(target, param):
		"""
		Checks whether the mode can be unset.  Returns a list of parameters, or None if the mode cannot be unset.
		For non-list modes, return a list of one item.
		For non-parameter modes, return an empty list.
		"""
	
	def apply(actionType, target, param, *params, **kw):
		"""
		Affect the mode should have.
		This is similar binding the appropriate actions directly, except that the IRCd will automatically determine
		whether the mode function should fire instead of making you figure that out.  This allows features like
		extbans to just work consistently across the board without every module having to try to implement them.
		A parameter is provided for the particular target to which the mode action is being applied.
		"""
	
	def showParam(user, target):
		"""
		Affects parameter modes only (ModeType.ParamOnUnset or ModeType.Param).  Returns how to display the mode
		parameter to users.
		"""
	
	def showListParams(user, target):
		"""
		Affects list modes only (ModeType.List).  Sends the parameter list to the user.  Returns None.
		"""

class Mode(object):
	affectedActions = []
	
	def checkSet(self, target, param):
		return [param]
	
	def checkUnset(self, target, param):
		return [param]
	
	def apply(self, actionType, target, param, *params, **kw):
		pass
	
	def showParam(self, user, target):
		return None
	
	def showListParams(self, user, target):
		pass