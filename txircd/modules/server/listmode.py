from twisted.plugin import IPlugin
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ModeType
from zope.interface import implements
from datetime import datetime

class ListModeSync(ModuleData, Command):
    implements(IPlugin, IModuleData, ICommand)
    
    name = "ListModeSync"
    core = True
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def serverCommands(self):
        return [ ("LISTMODE", 1, self) ]
    
    def parseParams(self, server, params, prefix, tags):
        if len(params) != 6:
            return None
        if params[0] in self.ircd.channels:
            if params[2] not in self.ircd.channelModeTypes:
                return None
            if self.ircd.channelModeTypes[params[2]] != ModeType.List:
                return None
            try:
                return {
                    "target": self.ircd.channels[params[0]],
                    "targettime": datetime.utcfromtimestamp(int(params[1])),
                    "mode": params[2],
                    "param": params[3],
                    "setter": params[4],
                    "modetime": datetime.utcfromtimestamp(int(params[5]))
                }
            except ValueError:
                return None
        elif params[0] in self.ircd.users:
            if params[2] not in self.ircd.userModeTypes:
                return None
            if self.ircd.userModeTypes[params[2]] != ModeType.List:
                return None
            try:
                return {
                    "target": self.ircd.users[params[0]],
                    "targettime": datetime.utcfromtimestamp(int(params[1])),
                    "mode": params[2],
                    "param": params[3],
                    "setter": params[4],
                    "modetime": datetime.utcfromtimestamp(int(params[5]))
                }
            except ValueError:
                return None
        return None
    
    def execute(self, server, data):
        targetTime = data["targettime"]
        try: # channels
            channel = data["target"]
            if targetTime <= channel.existedSince:
                if channel.addListMode(data["mode"], data["param"], data["setter"], data["modetime"]):
                    return True
            else:
                return True # We still handled it in a way that wasn't a desync
        except AttributeError:
            user = data["target"]
            if targetTime <= user.connectedSince:
                if user.addListMode(data["mode"], data["param"], data["setter"], data["modetime"]):
                    return True
            else:
                return True
        return None

listModeSync = ListModeSync()