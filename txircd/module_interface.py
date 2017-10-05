from zope.interface import Attribute, Interface
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

class IModuleData(Interface):
	name = Attribute("The module name.")
	requiredOnAllServers = Attribute("""
		Whether the module must be loaded on all servers in order to function properly.
		This is determined automatically in many cases, such as if the module provides modes
		or server commands.  If the IRCd determines that the module doesn't need to be loaded
		on all servers but it actually does, it will check this value.
		""")
	core = Attribute("Always false for custom modules.")
	
	def hookIRCd(ircd: "IRCd") -> None:
		"""
		Provides the IRCd instance to save and use later.
		"""
	
	def channelModes() -> List[Union[Tuple[str, "ModeType", "Mode"], Tuple[str, "ModeType", "Mode", int, str]]]:
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
	
	def userModes() -> List[Tuple[str, "ModeType", "Mode"]]:
		"""
		Returns the user modes provided by the module.  The modes are returned as a list
		of tuples:
		[ (letter, type, object) ]
		The letter is the letter of the mode.
		The type is a mode type, one of ModeType.List, ModeType.ParamOnUnset, ModeType.Param,
			and ModeType.NoParam.  (ModeType is in txircd.utils.)
		The object is an instance of the class that implements the mode.
		"""
	
	def actions() -> List[Tuple[str, int, Callable]]:
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
	
	def userCommands() -> List[Tuple[str, int, "Command"]]:
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
	
	def serverCommands() -> List[Tuple[str, int, "Command"]]:
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
	
	def load() -> None:
		"""
		Called when the module is successfully loaded.
		"""
	
	def rehash() -> None:
		"""
		Called when the server is rehashed.  Indicates that new configuration values are loaded
		and that any changes should be acted upon.
		"""
	
	def unload() -> Optional["Deferred"]:
		"""
		Called when the module is being unloaded for any reason, including to be reloaded.
		Should do basic cleanup.
		"""
	
	def fullUnload() -> Optional["Deferred"]:
		"""
		Called when the module is being fully unloaded with no intention to reload.
		Should do full cleanup of any data this module uses, including unsetting of modes
		handled by this module.
		"""

	def verifyConfig(config: Dict[str, Any]) -> None:
		"""
		Called when the module is loaded and when the server is rehashed.  Should check all
		configuration values defined by this module and either adjust them in the configuration
		or raise a ConfigValidationError when an invalid value is defined.
		"""

class ModuleData(object):
	requiredOnAllServers = False
	core = False
	
	def hookIRCd(self, ircd: "IRCd") -> None:
		self.ircd = ircd
	
	def channelModes(self) -> List[Union[Tuple[str, "ModeType", "Mode"], Tuple[str, "ModeType", "Mode", int, str]]]:
		return []
	
	def userModes(self) -> List[Tuple[str, "ModeType", "Mode"]]:
		return []
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return []
	
	def userCommands(self) -> List[Tuple[str, int, "Command"]]:
		return []
	
	def serverCommands(self) -> List[Tuple[str, int, "Command"]]:
		return []
	
	def load(self) -> None:
		pass
	
	def rehash(self) -> None:
		pass
	
	def unload(self) -> Optional["Deferred"]:
		pass
	
	def fullUnload(self) -> Optional["Deferred"]:
		pass
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
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
	burstQueuePriority = Attribute("""
		The priority of this command on the burst queue. Applies to server commands only.
		If the priority is None, the command is processed immediately instead of being
		placed on the burst queue.
		Otherwise, commands are processed in order from highest to lowest priority.
		""")
	
	def parseParams(source: Union["IRCUser", "IRCServer"], params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		"""
		Parses the parameters to the command.  Returns a dictionary of data, or None if
		the parameters cannot be properly parsed.
		"""
	
	def affectedUsers(source: Union["IRCUser", "IRCServer"], data: Dict[Any, Any]) -> List["IRCUser"]:
		"""
		Determines which users are affected given parsed command data to determine which
		action functions to call.
		Returns a list of users (or an empty list for no users).
		The user who issued the command is automatically added to this list if that user
		is not already in it.
		"""
	
	def affectedChannels(source: Union["IRCUser", "IRCServer"], data: Dict[Any, Any]) -> List["IRCChannel"]:
		"""
		Determines which channels are affected given parsed command data to determine
		which action functions to call.
		Returns a list of channels (or an empty list for no channels).
		"""
	
	def execute(source: Union["IRCUser", "IRCServer"], data: Dict[Any, Any]) -> Optional[bool]:
		"""
		Performs the command action.
		Returns True if successfully handled; otherwise defers to the next handler in the chain
		"""

class Command(object):
	resetsIdleTime = True
	forRegistered = True
	burstQueuePriority = None
	
	def parseParams(self, source: Union["IRCUser", "IRCServer"], params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return None
	
	def affectedUsers(self, source: Union["IRCUser", "IRCServer"], data: Dict[Any, Any]) -> List["IRCUser"]:
		return []
	
	def affectedChannels(self, source: Union["IRCUser", "IRCServer"], data: Dict[Any, Any]) -> List["IRCChannel"]:
		return []
	
	def execute(self, source: Union["IRCUser", "IRCServer"], data: Dict[Any, Any]) -> Optional[bool]:
		pass


class IMode(Interface):
	affectedActions = Attribute("""
		A dict of action types for which to trigger the mode handler. Each action type in
		the dict maps to a priority.
		""")
	
	def checkSet(target: Union["IRCUser", "IRCChannel"], param: str) -> Optional[List[str]]:
		"""
		Checks whether the mode can be set.  Returns a list of parameters, or None if the mode cannot be set.
		For non-list modes, return a list of one item.
		For non-parameter modes, return an empty list.
		"""
	
	def checkUnset(target: Union["IRCUser", "IRCChannel"], param: str) -> Optional[List[str]]:
		"""
		Checks whether the mode can be unset.  Returns a list of parameters, or None if the mode cannot be unset.
		For non-list modes, return a list of one item.
		For non-parameter modes, return an empty list.
		"""
	
	def apply(actionType: str, target: Union["IRCUser", "IRCChannel"], param: str, *params: Any) -> Any:
		"""
		Affect the mode should have.
		This is similar binding the appropriate actions directly, except that the IRCd will automatically determine
		whether the mode function should fire instead of making you figure that out.  This allows features like
		extbans to just work consistently across the board without every module having to try to implement them.
		A parameter is provided for the particular target to which the mode action is being applied.
		"""
	
	def showParam(user: "IRCUser", target: Union["IRCUser", "IRCChannel"]) -> str:
		"""
		Affects parameter modes only (ModeType.ParamOnUnset or ModeType.Param).  Returns how to display the mode
		parameter to users.
		"""
	
	def showListParams(user: "IRCUser", target: Union["IRCUser", "IRCChannel"]) -> None:
		"""
		Affects list modes only (ModeType.List).  Sends the parameter list to the user.  Returns None.
		"""

class Mode(object):
	affectedActions = []
	
	def checkSet(self, target: Union["IRCUser", "IRCChannel"], param: str) -> Optional[List[str]]:
		return [param]
	
	def checkUnset(self, target: Union["IRCUser", "IRCChannel"], param: str) -> Optional[List[str]]:
		return [param]
	
	def apply(self, actionType: str, target: Union["IRCUser", "IRCChannel"], param: str, *params: Any, **kw: Any) -> Any:
		pass
	
	def showParam(self, user: "IRCUser", target: Union["IRCUser", "IRCChannel"]) -> str:
		return None
	
	def showListParams(self, user: "IRCUser", target: Union["IRCUser", "IRCChannel"]) -> None:
		pass