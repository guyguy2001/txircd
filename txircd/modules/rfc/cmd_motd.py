from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import splitMessage
from zope.interface import implements

class MessageOfTheDay(ModuleData, Command):
    implements(IPlugin, IModuleData)
    
    name = "MOTD"
    core = True
    motd = []
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("welcome", 5, self.showMOTD),
                ("sendremoteusermessage-372", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_MOTD, *params, **kw)),
                ("sendremoteusermessage-375", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_MOTDSTART, *params, **kw)),
                ("sendremoteusermessage-376", 1, lambda user, *params, **kw: self.pushMessage(user, irc.RPL_ENDOFMOTD, *params, **kw)),
                ("sendremoteusermessage-422", 1, lambda user, *params, **kw: self.pushMessage(user, irc.ERR_NOMOTD, *params, **kw)) ]
    
    def userCommands(self):
        return [ ("MOTD", 1, UserMOTD(self.ircd, self.showMOTD)) ]
    
    def serverCommands(self):
        return [ ("MOTDREQ", 1, ServerMOTDRequest(self.ircd, self.showMOTD)) ]
    
    def load(self):
        self.rehash()
    
    def rehash(self):
        self.motd = []
        try:
            with open(self.ircd.config["motd_file"], "r") as motdFile:
                for line in motdFile:
                    for outputLine in splitMessage(line, 400):
                        self.motd.append(outputLine)
        except (IOError, KeyError):
            pass # The MOTD list is already in the condition such that it will be reported as "no MOTD", so we're fine here
    
    def showMOTD(self, user):
        if not self.motd:
            user.sendMessage(irc.ERR_NOMOTD, ":Message of the day file is missing.")
        else:
            user.sendMessage(irc.RPL_MOTDSTART, ":{} Message of the Day".format(self.ircd.config["network_name"]))
            for line in self.motd:
                user.sendMessage(irc.RPL_MOTD, ":{}".format(line))
            user.sendMessage(irc.RPL_ENDOFMOTD, ":End of message of the day")
    
    def pushMessage(self, user, numeric, *params, **kw):
        server = self.ircd.servers[user.uuid[:3]]
        server.sendMessage("PUSH", user.uuid, "::{} {} {}".format(self.ircd.name, numeric, " ".join(params)), prefix=self.ircd.serverID)
        return True

class UserMOTD(Command):
    implements(ICommand)
    
    def __init__(self, ircd, motdFunc):
        self.ircd = ircd
        self.motdFunc = motdFunc
    
    def parseParams(self, user, params, prefix, tags):
        if params and params[0] != self.ircd.name:
            if params[0] not in self.ircd.serverNames:
                user.sendSingleError("MOTDServer", irc.ERR_NOSUCHSERVER, params[0], ":No such server")
                return None
            return {
                "server": self.ircd.servers[self.ircd.serverNames[params[0]]]
            }
        return {}
    
    def execute(self, user, data):
        if not data:
            self.motdFunc(user)
            return True
        data["server"].sendMessage("MOTDREQ", prefix=user.uuid)
        return True

class ServerMOTDRequest(Command):
    implements(ICommand)
    
    def __init__(self, ircd, motdFunc):
        self.ircd = ircd
        self.motdFunc = motdFunc
    
    def parseParams(self, server, params, prefix, tags):
        if params:
            return None
        if prefix not in self.ircd.users:
            return None
        return {
            "user": self.ircd.users[prefix]
        }
    
    def execute(self, server, data):
        user = data["user"]
        self.motdFunc(user) # This will send the MOTD normally, and the message will get pushed by our pushMessage function to the user
        return True

motdHandler = MessageOfTheDay()