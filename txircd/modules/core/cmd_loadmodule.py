from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.ircd import ModuleLoadError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

# We're using the InspIRCd numerics, as they seem to be the only ones to actually use numerics
irc.ERR_CANTLOADMODULE = "974"
irc.RPL_LOADEDMODULE = "975"

class LoadModuleCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)

    name = "LoadModuleCommand"
    core = True

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def actions(self):
        return [ ("commandpermission-LOADMODULE", 1, self.restrictToOpers) ]

    def userCommands(self):
        return [ ("LOADMODULE", 1, self) ]

    def restrictToOpers(self, user, command, data):
        if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-loadmodule", users=[user]):
            user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
            return False
        return None

    def parseParams(self, user, params, prefix, tags):
        if not params:
            user.sendSingleError("LoadModuleCmd", irc.ERR_NEEDMOREPARAMS, "LOADMODULE", ":Not enough parameters")
            return None
        return {
            "modulename": params[0]
        }

    def execute(self, user, data):
        moduleName = data["modulename"]
        if moduleName in self.ircd.loadedModules:
            user.sendMessage(irc.ERR_CANTLOADMODULE, moduleName, ":Module is already loaded")
        else:
            try:
                self.ircd.loadModule(moduleName)
                if moduleName in self.ircd.loadedModules:
                    user.sendMessage(irc.RPL_LOADEDMODULE, moduleName, ":Module successfully loaded")
                else:
                    user.sendMessage(irc.ERR_CANTLOADMODULE, moduleName, ":No such module")
            except ModuleLoadError as e:
                user.sendMessage(irc.ERR_CANTLOADMODULE, moduleName, ":{}".format(e.message))
        return True

loadmoduleCommand = LoadModuleCommand()