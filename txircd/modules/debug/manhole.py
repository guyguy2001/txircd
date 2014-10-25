from twisted.conch.manhole_tap import makeService
from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class Manhole(ModuleData):
    implements(IModuleData)
    
    name = "Manhole"
    
    manhole = None
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def load(self):
        self.manhole = makeService({
            "namespace": { "ircd": self.ircd },
            "passwd": self.ircd.config.getWithDefault("manhole_passwd", "manhole.passwd"),
            "telnetPort": self.ircd.config.getWithDefault("manhole_bind_telnet", None),
            "sshPort": self.ircd.config.getWithDefault("manhole_bind_ssh", None)
        })
        self.manhole.startService()
    
    def unload(self):
        return self.manhole.stopService()

manhole = Manhole()