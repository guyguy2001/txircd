from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class QuitCommand(ModuleData, Command):
    implements(IPlugin, IModuleData)
    
    name = "QuitCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def userCommands(self):
        return [ ("QUIT", 1, UserQuit(self.ircd)) ]
    
    def serverCommands(self):
        return [ ("QUIT", 1, ServerQuit(self.ircd)) ]

class UserQuit(Command):
    implements(ICommand)
    
    forRegisteredUsers = None
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if not params or not params[0]:
            user.sendMessage(irc.ERR_NEEDMOREPARAMS, "QUIT", ":Not enough parameters")
            return None
        return {
            "reason": params[0][:self.ircd.config.getWithDefault("quit_msg_length", 255)]
        }
    
    def execute(self, user, data):
        user.disconnect("Quit: {}".format(data["reason"]))
        return True

class ServerQuit(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, server, params, prefix, tags):
        if prefix not in self.ircd.users:
            return None
        if len(params) != 1:
            return None
        return {
            "user": self.ircd.users[prefix],
            "reason": params[0]
        }
    
    def execute(self, server, data):
        data["user"].disconnect(data["reason"], True)
        return True

quitCommand = QuitCommand()