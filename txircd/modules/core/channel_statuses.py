from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class StatusReport(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "StatusReport"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("channelstatuses", 1, self.statuses) ]
    
    def statuses(self, channel, user):
        if user not in channel.users:
            return None
        if not channel.users[user]:
            return ""
        return self.ircd.channelStatuses[channel.users[user][0]][0]

statuses = StatusReport()