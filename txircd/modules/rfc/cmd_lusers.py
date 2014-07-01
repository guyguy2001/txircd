from twisted.internet.task import LoopingCall
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.RPL_LOCALUSERS = "265"
irc.RPL_GLOBALUSERS = "266"

class LUsersCommand(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "LUsersCommand"
    core = True
    
    currentUsers = None
    currentInvisible = None
    currentServers = None
    currentOpers = None
    currentChannels = None
    localUsers = None
    localServers = None
    
    syncTimer = None
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("welcome", 6, lambda user: self.execute(user, {})),
                ("register", 10, self.addUser),
                ("quit", 10, self.removeUser),
                ("remoteregister", 10, self.addRemoteUser),
                ("remotequit", 10, self.removeRemoteUser),
                ("modechange-user-o", 10, self.toggleOper),
                ("modechange-user-i", 10, self.toggleInvisible),
                ("channelcreate", 10, self.addChannel),
                ("channeldestroy", 10, self.removeChannel),
                ("serverconnect", 10, self.addServer),
                ("serverquit", 10, self.removeServer) ]
    
    def userCommands(self):
        return [ ("LUSERS", 1, self) ]
    
    def load(self):
        if "users_localmax" not in self.ircd.storage:
            self.ircd.storage["users_localmax"] = 0
        if "users_globalmax" not in self.ircd.storage:
            self.ircd.storage["users_globalmax"] = 0
        self.syncTimer = LoopingCall(self.recountStats)
        self.syncTimer.start(3600, True) # Resync the statistics every hour just in case
    
    def unload(self):
        self.syncTimer.stop()
    
    def addUser(self, user):
        self.currentUsers += 1
        self.localUsers += 1
        self.compareUsersToMax()
        self.compareLocalUsersToMax()
        return True
    
    def removeUser(self, user, reason):
        if "i" in user.modes:
            self.currentInvisible -= 1
        else:
            self.currentUsers -= 1
        self.localUsers -= 1
    
    def addRemoteUser(self, user):
        self.currentUsers += 1
        self.compareUsersToMax()
    
    def removeRemoteUser(self, user, reason):
        if "i" in user.modes:
            self.currentInvisible -= 1
        else:
            self.currentUsers -= 1
    
    def toggleOper(self, user, source, adding, param):
        if adding:
            self.currentOpers += 1
        else:
            self.currentOpers -= 1
    
    def toggleInvisible(self, user, source, adding, param):
        if adding:
            self.currentInvisible += 1
            self.currentUsers -= 1
        else:
            self.currentInvisible -= 1
            self.currentUsers += 1
    
    def addChannel(self, channel, user):
        self.currentChannels += 1
    
    def removeChannel(self, channel):
        self.currentChannels -= 1
    
    def addServer(self, server):
        self.currentServers += 1
        if server.nextClosest == self.ircd.serverID:
            self.localServers += 1
    
    def removeServer(self, server, reason):
        self.currentServers -= 1
        if server.nextClosest == self.ircd.serverID:
            self.localServers -= 1
    
    def compareUsersToMax(self):
        if self.currentUsers + self.currentInvisible > self.ircd.storage["users_globalmax"]:
            self.ircd.storage["users_globalmax"] = self.currentUsers + self.currentInvisible
    
    def compareLocalUsersToMax(self):
        if self.localUsers > self.ircd.storage["users_localmax"]:
            self.ircd.storage["users_localmax"] = self.localUsers
    
    def recountStats(self):
        self.currentUsers = 0
        self.currentInvisible = 0
        self.currentServers = 1 # Include self in the server count
        self.currentOpers = 0
        self.currentChannels = len(self.ircd.channels)
        self.localUsers = 0
        self.localServers = 0
        
        for user in self.ircd.users.itervalues():
            if "i" in user.modes:
                self.currentInvisible += 1
            else:
                self.currentUsers += 1
            if "o" in user.modes:
                self.currentOpers += 1
            if user.uuid[:3] == self.ircd.serverID:
                self.localUsers += 1
        
        for server in self.ircd.servers.itervalues():
            self.currentServers += 1
            if server.nextClosest == self.ircd.serverID:
                self.localServers += 1
        
        if self.localUsers > self.ircd.storage["users_localmax"]:
            self.ircd.storage["users_localmax"] = self.localUsers
        if self.currentUsers + self.currentInvisible > self.ircd.storage["users_globalmax"]:
            self.ircd.storage["users_globalmax"] = self.currentUsers + self.currentInvisible
    
    def parseParams(self, user, params, prefix, tags):
        return {}
    
    def execute(self, user, data):
        user.sendMessage(irc.RPL_LUSERCLIENT, ":There are {} users and {} invisible on {} servers".format(self.currentUsers, self.currentInvisible, self.currentServers))
        user.sendMessage(irc.RPL_LUSEROP, str(self.currentOpers), ":operator{} online".format("" if self.currentOpers == 1 else "s"))
        user.sendMessage(irc.RPL_LUSERCHANNELS, str(self.currentChannels), ":channel{} formed".format("" if self.currentChannels == 1 else "s"))
        user.sendMessage(irc.RPL_LUSERME, ":I have {} clients and {} servers".format(self.localUsers, self.localServers))
        user.sendMessage(irc.RPL_LOCALUSERS, ":Current Local Users: {}  Max: {}".format(self.localUsers, self.ircd.storage["users_localmax"]))
        user.sendMessage(irc.RPL_GLOBALUSERS, ":Current Global Users: {}  Max: {}".format(self.currentUsers + self.currentInvisible, self.ircd.storage["users_globalmax"]))
        return True

lusersCmd = LUsersCommand()