from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.user import RemoteUser
from txircd.utils import ModeType, now, timestamp
from zope.interface import implements
from datetime import datetime

# :<sid of new users server> UID <uid> <timestamp> <nick> <hostname> <displayed-hostname> <ident> <ip> <signon time> +<modes {mode params}> :<gecos>

class ServerUID(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "ServerUID"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("welcome", 500, self.broadcastUID) ]
    
    def serverCommands(self):
        return [ ("UID", 1, self) ]
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) < 10:
            return None
        uuid, ts, nick, realHost, displayHost, ident, ip, signonTs = params[:8]
        msgTime = datetime.utcfromtimestamp(int(ts))
        connectTime = datetime.utcfromtimestamp(int(signonTs))
        sourceServer = self.ircd.servers[uuid[:3]]
        currParam = 10
        modes = {}
        for mode in params[9]:
            if mode == "+":
                continue
            try:
                modeType = self.ircd.userModeTypes[mode]
            except KeyError:
                return None # There's a mode that's NOT REAL so get out of here
            param = None
            if modeType in (ModeType.List, ModeType.ParamOnUnset, ModeType.Param):
                param = params[currParam]
                currParam += 1
                if not param or " " in param:
                    return None
            if modeType == ModeType.List:
                if mode not in modes:
                    modes[mode] = []
                modes[mode].append((param, sourceServer.name, msgTime))
            else:
                modes[mode] = param
        gecos = params[currParam]
        return {
            "uuid": uuid,
            "time": msgTime,
            "nick": nick,
            "ident": ident,
            "host": realHost,
            "displayhost": displayHost,
            "ip": ip,
            "gecos": gecos,
            "connecttime": connectTime,
            "modes": modes
        }
    
    def execute(self, server, data):
        msgTime = data["time"]
        connectTime = data["connecttime"]
        newUser = RemoteUser(self.ircd, data["ip"], data["uuid"], data["host"])
        newUser.changeHost(data["displayhost"], True)
        newUser.changeIdent(data["ident"], True)
        newUser.changeNick(data["nick"], True)
        newUser.changeGecos(data["gecos"], True)
        newUser.connectedSince = connectTime
        newUser.nickSince = msgTime
        newUser.idleSince = msgTime
        newUser.register("USER")
        newUser.register("NICK")
        return True
    
    def broadcastUID(self, user):
        modeStr = "+{}".format(user.modeString(None))
        finalGecos = ":{}".format(user.gecos)
        currentTimestamp = str(timestamp(now()))
        signonTimestamp = str(timestamp(user.connectedSince))
        for server in self.ircd.servers.itervalues():
            if server.nextClosest == self.ircd.serverID:
                server.sendMessage("UID", user.uuid, currentTimestamp, user.nick, user.realHost, user.host, user.ident, user.ip, signonTimestamp, modeStr, finalGecos, prefix=self.ircd.serverID)

serverUID = ServerUID()