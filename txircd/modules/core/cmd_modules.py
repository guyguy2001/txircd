from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

# Using the RatBox numerics (and names) here, which most IRCds seem to use
irc.RPL_MODLIST = "702"
irc.RPL_ENDOFMODLIST = "703"

class ModulesCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)

    name = "ModulesCommand"
    core = True

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def userCommands(self):
        return [ ("MODULES", 1, self) ]

    def parseParams(self, user, params, prefix, tags):
        return {}

    def execute(self, user, data):
        for module in sorted(self.ircd.loadedModules.keys()):
            user.sendMessage(irc.RPL_MODLIST, ":{}".format(module))
        user.sendMessage(irc.RPL_ENDOFMODLIST, ":End of MODULES list")
        return True

modulesCommand = ModulesCommand()