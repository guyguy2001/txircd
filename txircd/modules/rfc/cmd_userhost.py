from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class UserhostCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "UserhostCommand"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def userCommands(self):
        return [ ("USERHOST", 1, self) ]
    
    def parseParams(self, user, params, prefix, tags):
        if not params:
            user.sendSingleError("UserhostParams", irc.ERR_NEEDMOREPARAMS, "USERHOST", ":Not enough parameters")
            return None
        return {
            "nicks": params[:5]
        }
    
    def execute(self, user, data):
        userHosts = []
        for nick in data["nicks"]:
            if nick not in self.ircd.userNicks:
                continue
            targetUser = self.ircd.users[self.ircd.userNicks[nick]]
            output = targetUser.nick
            if "o" in targetUser.modes:
                output += "*"
            output += "="
            if "away" in user.metadata["ext"]:
                output += "-"
            else:
                output += "+"
            output += "{}@{}".format(targetUser.ident, targetUser.host)
            userHosts.append(output)
        user.sendMessage(irc.RPL_USERHOST, ":{}".format(" ".join(userHosts)))
        return True

userhostCmd = UserhostCommand()