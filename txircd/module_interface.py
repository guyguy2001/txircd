from zope.interface import Attribute, Interface

class IModuleData(Interface):
    name = Attribute("The module name.")
    requiredOnAllServers = Attribute("""
        Whether the module must be loaded on all servers in order to function properly.
        This is determined automatically in many cases, such as if the module provides modes
        or server commands.  If the IRCd determines that the module doesn't need to be loaded
        on all servers but it actually does, it will check this value.
        """)
    
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
        Returns the actions this module handles.  The actions are returned as a dictionary:
        { name => function }
        The name is the name of the action as a string.
        The function is a reference to the function which handles the action.
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

class ModuleData(object):
    requiredOnAllServers = False
    
    def hookIRCd(self, ircd):
        pass
    
    def channelModes(self):
        return []
    
    def userModes(self):
        return []
    
    def actions(self):
        return {}
    
    def userCommands(self):
        return []
    
    def serverCommands(self):
        return []


class ICommand(Interface):
    resetsIdleTime = Attribute("Whether this command resets the user's idle time.")
    
    def parseParams(params):
        """
        Parses the parameters to the command.  Returns a dictionary of data, or None if
        the parameters cannot be properly parsed.
        """
    
    def execute(user, data):
        """
        Performs the command action.
        """

class Command(object):
    resetsIdleTime = True
    
    def parseParams(self, params):
        return None
    
    def execute(self, user, data):
        pass


class IMode(Interface):
    affectedActions = Attribute("A list of action types for which to trigger the mode handler.")
    
    def checkSet(param):
        """
        Checks whether the mode can be set.  Returns a list of parameters, or None if the mode cannot be set.
        For non-list modes, return a list of one item.
        For non-parameter modes, return an empty list.
        """
    
    def checkUnset(param):
        """
        Checks whether the mode can be unset.  Returns a list of parameters, or None if the mode cannot be unset.
        For non-list modes, return a list of one item.
        For non-parameter modes, return an empty list.
        """
    
    def apply(actionType, *actionParams):
        """
        Affect the mode should have.
        This is similar binding the appropriate actions directly, except that the IRCd will automatically determine
        whether the mode function should fire instead of making you figure that out.  This allows features like
        extbans to just work consistently across the board without every module having to try to implement them.
        """
    
    def showParam(user, channel):
        """
        Affects channel parameter modes only (ModeType.ParamOnUnset or ModeType.Param).  Returns how to display the
        mode parameter to users.
        """
    
    def showListParams(user, channel):
        """
        Affects list modes only (ModeType.List).  Sends the parameter list to the user.  Returns None.
        For user modes, the channel parameter is None.
        """

class Mode(object):
    affectedActions = []
    
    def checkSet(self, param):
        return [param]
    
    def checkUnset(self, param):
        return [param]
    
    def apply(self, actionType, *actionParams):
        pass
    
    def showParam(self, user, channel):
        return ""
    
    def showListParams(self, user, channel):
        pass