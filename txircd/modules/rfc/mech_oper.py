from twisted.plugin import IPlugin
from twisted.python import log
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ircLower, ModeType
from zope.interface import implements
from fnmatch import fnmatch
import logging

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
        if "o" not in user.modes:
            # Maybe the user de-opered or something, but if they did they're clearly not an oper now
            return False
        # Check for oper permissions in the user's permission storage
        if "oper-permissions" not in user.cache:
            return False
        return permissionType in user.cache["oper-permissions"]
    
    def nope(self, user, settingUser, adding, param):
        if adding:
            user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - User mode o may not be set")
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
        if "types" in operData:
            configuredOperTypes = self.ircd.config.getWithDefault("oper_types", {})
            operPermissions = set()
            for type in operData["types"]:
                if type not in configuredOperTypes:
                    continue
                operPermissions.update(configuredOperTypes[type])
            user.cache["oper-permissions"] = operPermissions
        return True

oper = Oper()