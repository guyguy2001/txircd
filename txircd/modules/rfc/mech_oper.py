from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ircLower, ModeType
from zope.interface import implements
from fnmatch import fnmatch

class Oper(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "Oper"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def userCommands(self):
        return [ ("OPER", 1, UserOper(self.ircd)) ]
    
    def actions(self):
        return [ ("userhasoperpermission", 1, self.operPermission),
         ("modepermission-user-o", 1, self.nope) ]
    
    def userModes(self):
        return [ ("o", ModeType.NoParam, self) ]
    
    def operPermission(self, user, permissionType):
        # For now, we're just going to check for usermode +o
        # Later, when we add a permission system, this can be expanded
        return "o" in user.modes
    
    def nope(self, user, settingUser, adding, param):
        if adding:
            return False
        return None

class UserOper(Command):
    implements(ICommand)
    
    def __init__(self, ircd):
        self.ircd = ircd
    
    def parseParams(self, user, params, prefix, tags):
        if len(params) < 2:
            user.sendSingleError("OperCmd", irc.ERR_NEEDMOREPARAMS, "OPER", ":Not enough parameters")
            return None
        return {
            "username": params[0],
            "password": params[1]
        }
    
    def execute(self, user, data):
        configuredOpers = self.ircd.config.getWithDefault("opers", {})
        username = data["username"]
        if username not in configuredOpers:
            user.sendMessage(irc.ERR_NOOPERHOST, ":Invalid oper credentials")
            return True
        operData = configuredOpers[username]
        if "password" not in operData:
            user.sendMessage(irc.ERR_NOOPERHOST, ":Invalid oper credentials")
            return True
        password = data["password"]
        if "hash" in operData:
            compareFunc = "compare-{}".format(operData["hash"])
            if compareFunc not in self.ircd.functionCache:
                user.sendMessage(irc.ERR_NOOPERHOST, ":Invalid oper credentials")
                return True
            passwordMatch = self.ircd.functionCache[compareFunc](password, operData["password"])
        else:
            passwordMatch = (password == operData["password"])
        if not passwordMatch:
            user.sendMessage(irc.ERR_NOOPERHOST, ":Invalid oper credentials")
            return True
        if "host" in operData:
            operHost = ircLower(operData["host"])
            userHost = ircLower("{}@{}".format(user.ident, user.host))
            if not fnmatch(userHost, operHost):
                userHost = ircLower("{}@{}".format(user.ident, user.realhost))
                if not fnmatch(userHost, operHost):
                    userHost = ircLower("{}@{}".format(user.ident, user.ip))
                    if not fnmatch(userHost, operHost):
                        user.sendMessage(irc.ERR_NOOPERHOST, ":Invalid oper credentials")
                        return True
        if self.ircd.runActionUntilFalse("opercheck", user, username, password, operData): # Allow other modules to implement additional checks
            user.sendMessage(irc.ERR_NOOPERHOST, ":Invalid oper credentials")
            return True
        user.setModes(self.ircd.serverID, "+o", [])
        user.sendMessage(irc.RPL_YOUREOPER, ":You are now an IRC operator")
        return True

oper = Oper()