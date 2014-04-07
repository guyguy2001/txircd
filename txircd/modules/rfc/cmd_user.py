from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class UserCommand(Command, ModuleData):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "UserCommand"
    core = True
    forRegisteredUsers = False
    
    def userCommands(self):
        return [ ("USER", 1, self) ]
    
    def parseParams(self, user, params, prefix, tags):
        if len(params) < 4:
            user.sendSingleCommandError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", ":Not enough parameters")
            return None
        if not params[3]: # Make sure the gecos isn't an empty string
            user.sendSingleCommandError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", ":Not enough parameters")
            return None
        for char in params[0]: # Validate the ident
            if not char.isalnum() and char not in "-.[\]^_`{|}":
                user.sendSingleCommandError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", ":Your username is not valid") # The RFC is dumb.
                return None
        return {
            "ident": params[0],
            "gecos": params[3]
        }
    
    def execute(self, user, data):
        user.changeIdent(data["ident"])
        user.changeGecos(data["gecos"])
        user.register("USER")
        return True

cmd_user = UserCommand()