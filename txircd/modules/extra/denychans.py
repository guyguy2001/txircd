from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements
from fnmatch import fnmatch

class DenyChannels(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "DenyChannels"
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def actions(self):
        return [ ("joinpermission", 10, self.blockNonDenied) ]
    
    def blockNonDenied(self, channel, user):
        if self.ircd.runActionUntilValue("userhasoperpermission", user, "channel-denied") is True:
            return None
        deniedChannels = self.ircd.config.getWithDefault("deny_channels", [])
        allowedChannels = self.ircd.config.getWithDefault("allow_channels", [])
        for name in allowedChannels:
            if fnmatch(channel.name, name):
                return None
        for name in deniedChannels:
            if fnmatch(channel.name, name):
                return False
        return None

denyChans = DenyChannels()