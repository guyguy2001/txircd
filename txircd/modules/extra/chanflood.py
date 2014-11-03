from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, now
from zope.interface import implements
from datetime import timedelta
from weakref import WeakKeyDictionary

class ChannelFlood(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "ChannelFlood"
    affectedActions = [ "commandextra-PRIVMSG", "commandextra-NOTICE" ]
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def channelModes(self):
        return [ ("f", ModeType.Param, self) ]
    
    def actions(self):
        return [ ("modeactioncheck-channel-f-commandextra-PRIVMSG", 10, self.channelHasMode),
                ("modeactioncheck-channel-f-commandextra-NOTICE", 10, self.channelHasMode) ]
    
    def channelHasMode(self, channel, user, command, data):
        if "f" in channel.modes:
            return channel.modes["f"]
        return None
    
    def checkSet(self, channel, param):
        if param.count(":") != 1:
            return None
        lines, seconds = param.split(":")
        try:
            lines = int(lines)
            seconds = int(seconds)
        except ValueError:
            return None
        if lines < 1 or seconds < 1:
            return None
        return [param]
    
    def apply(self, actionName, channel, param, user, command, data):
        if "targetchans" not in data or channel not in data["targetchans"]:
            return
        if "floodhistory" not in user.cache:
            user.cache["floodhistory"] = WeakKeyDictionary()
        if channel not in user.cache["floodhistory"]:
            user.cache["floodhistory"][channel] = []
        
        currentTime = now()
        user.cache["floodhistory"][channel].append((data["targetchans"][channel], currentTime))
        maxLines, seconds = param.split(":")
        maxLines = int(maxLines)
        seconds = int(seconds)
        duration = timedelta(seconds=seconds)
        floodTime = currentTime - duration
        floodHistory = user.cache["floodhistory"][channel]
        
        while floodHistory:
            if floodHistory[0][1] <= floodTime:
                del floodHistory[0]
            else:
                break
        user.cache["floodhistory"][channel] = floodHistory
        if len(floodHistory) > maxLines:
            for server in self.ircd.servers.itervalues():
                if server.nextClosest == self.ircd.serverID:
                    server.sendMessage("KICK", channel.name, user.uuid, ":Channel flood limit reached", prefix=self.ircd.serverID)
            for u in channel.users.iterkeys():
                if u.uuid[:3] == self.ircd.serverID:
                    u.sendMessage("KICK", user.nick, ":Channel flood limit reached", to=channel.name)
            user.leaveChannel(channel)

chanFlood = ChannelFlood()