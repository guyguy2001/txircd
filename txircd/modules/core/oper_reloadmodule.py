from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

# We're using the InspIRCd numerics, as they seem to be the only ones to actually use numerics
irc.ERR_CANTUNLOADMODULE = "972"
irc.RPL_LOADEDMODULE = "975"

class ReloadModuleCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)

    name = "ReloadModuleCommand"
    core = True

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def actions(self):
        return [ ("commandpermission-RELOADMODULE", 1, self.restrictToOpers) ]

    def userCommands(self):
        return [ ("RELOADMODULE", 1, self) ]

    def restrictToOpers(self, user, command, data):
        if not self.ircd.runActionUntilValue("userhasoperpermission", user, "command-reloadmodule", users=[user]):
            user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
            return False
        return None

    def parseParams(self, user, params, prefix, tags):
        if not params:
            user.sendSingleError("ReloadModuleCmd", irc.ERR_NEEDMOREPARAMS, "RELOADMODULE", ":Not enough parameters")
            return None
        return {
            "modulename": params[0]
        }

    def execute(self, user, data):
        moduleName = data["modulename"]
        if moduleName not in self.ircd.loadedModules:
            user.sendMessage(irc.ERR_CANTUNLOADMODULE, moduleName, ":No such module")
        else:
            try:
                self.ircd.reloadModule(moduleName)
                user.sendMessage(irc.RPL_LOADEDMODULE, moduleName, ":Module successfully reloaded")
            except ValueError as e:
                user.sendMessage(irc.ERR_CANTUNLOADMODULE, moduleName, ":{}; module is now unloaded".format(e.message))
        return True

reloadmoduleCommand = ReloadModuleCommand()