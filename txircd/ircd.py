from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import DeferredList
from twisted.internet.endpoints import serverFromString
from twisted.plugin import getPlugins
from twisted.python import log
from txircd.config import Config
from txircd.factory import ServerListenFactory, UserFactory
from txircd.module_interface import IModuleData
from txircd.utils import ModeType, unescapeEndpointDescription
import logging, txircd.modules

class IRCd(Service):
    def __init__(self, configFileName):
        self.config = Config(configFileName)
        self.boundPorts = {}
        self.loadedModules = {}
        self._loadedModuleData = {}
        self.commonModules = set()
        self.userCommands = {}
        self.serverCommands = {}
        self.channelModes = ({}, {}, {}, {})
        self.channelStatuses = {}
        self.channelStatusSymbols = {}
        self.channelModeTypes = {}
        self.userModes = ({}, {}, {}, {})
        self.userModeTypes = {}
        self.actions = {}
    
    def startService(self):
        log.msg("Loading modules...", logLevel=logging.INFO)
        self._loadModules()
        log.msg("Binding ports...", logLevel=logging.INFO)
        for bindDesc in self.config["bind_client"]:
            try:
                endpoint = serverFromString(reactor, unescapeEndpointDescription(bindDesc))
            except ValueError as e:
                log.msg(str(e), logLevel=logging.ERROR)
                continue
            listenDeferred = endpoint.listen(UserFactory(self))
            listenDeferred.addCallback(self._savePort, bindDesc)
            listenDeferred.addErrback(self._logNotBound, bindDesc)
        for bindDesc in self.config["bind_server"]:
            try:
                endpoint = serverFromString(reactor, unescapeEndpointDescription(bindDesc))
            except ValueError as e:
                log.msg(str(e), logLevel=logging.ERROR)
                continue
            listenDeferred = endpoint.listen(ServerListenFactory(self))
            listenDeferred.addCallback(self._savePort, bindDesc)
            listenDeferred.addErrback(self._logNotBound, bindDesc)
        log.msg("txircd started!", logLevel=logging.INFO)
    
    def stopService(self):
        stopDeferreds = []
        for port in self.boundPorts.itervalues():
            d = port.stopListening()
            if d:
                stopDeferreds.append(d)
        return DeferredList(stopDeferreds)
    
    def _savePort(self, port, desc):
        self.boundPorts[desc] = port
    
    def _logNotBound(self, err, desc):
        log.msg("Could not bind '{}': {}".format(desc, err), logLevel=logging.ERROR)
    
    def _loadModules(self):
        for module in getPlugins(IModuleData, txircd.modules):
            if module.name in self.loadedModules:
                continue
            if module.core or module.name in self.config["modules"]:
                self.loadModule(module)
    
    def loadModule(self, module):
        if not IModuleData.providedBy(module):
            raise ModuleLoadError ("???", "Module does not implement module interface")
        if not module.name:
            raise ModuleLoadError ("???", "Module did not provide a name")
        if module.name in self.loadedModules:
            return
        module.hookIRCd(self)
        moduleData = {
            "channelmodes": module.channelModes(),
            "usermodes": module.userModes(),
            "actions": module.actions(),
            "usercommands": module.userCommands(),
            "servercommands": module.serverCommands()
        }
        newChannelModes = ({}, {}, {}, {})
        newChannelStatuses = {}
        newUserModes = ({}, {}, {}, {})
        newActions = moduleData["actions"]
        newUserCommands = {}
        newServerCommands = {}
        common = False
        for mode in moduleData["channelmodes"]:
            if mode[0] in self.channelModeTypes:
                raise ModuleLoadError (module.name, "Tries to implement channel mode +{} when that mode is already implemented.".format(mode[0]))
            if mode[1] == ModeType.Status:
                if mode[4] in self.channelStatusSymbols:
                    raise ModuleLoadError (module.name, "Tries to create a channel rank with symbol {} when that symbol is already in use.".format(mode[4]))
                try:
                    newChannelStatuses[mode[0]] = (mode[4], mode[3], mode[2])
                except IndexError:
                    raise ModuleLoadError (module.name, "Specifies channel status mode {} without a rank or symbol".format(mode[0]))
            else:
                newChannelModes[mode[1]][mode[0]] = mode[2]
            common = True
        for mode in moduleData["usermodes"]:
            if mode[0] in self.userModeTypes:
                raise ModuleLoadError (module.name, "Tries to implement user mode +{} when that mode is already implemented.".format(mode[0]))
            newUserModes[mode[1]][mode[0]] = mode[2]
            common = True
        for command in moduleData["usercommands"]:
            if command[0] not in newUserCommands:
                newUserCommands[command[0]] = []
            newUserCommands[command[0]].append((command[2], command[1]))
        for command in moduleData["servercommands"]:
            if command[0] not in newServerCommands:
                newServerCommands[command[0]] = []
            newServerCommands[command[0]].append((command[2], command[1]))
            common = True
        if not common:
            common = module.requiredOnAllServers
        
        self.loadedModules[module.name] = module
        self._loadedModuleData[module.name] = moduleData
        if common:
            self.commonModules.add(module.name)
        
        if "moduleload" in self.actions:
            for action in self.actions["moduleload"]:
                action(module.name)
        
        for type, typeSet in enumerate(newChannelModes):
            for mode, implementation in typeSet.iteritems():
                self.channelModeTypes[mode] = type
                self.channelModes[type][mode] = implementation
        for mode, data in newChannelStatuses.iteritems():
            self.channelModeTypes[mode] = ModeType.Status
            self.channelStatuses[mode] = data
            self.channelStatusSymbols[data[4]] = mode
        for type, typeSet in enumerate(newUserModes):
            for mode, implementation in typeSet.iteritems():
                self.userModeTypes[mode] = type
                self.userModes[type][mode] = implementation
        for action, function in newActions.iteritems():
            if action not in self.actions:
                self.actions[action] = []
            self.actions[action].append(function)
        for command, data in newUserCommands:
            if command not in self.userCommands:
                self.userCommands[command] = [data]
            else:
                for index, cmd in enumerate(self.userCommands[command]):
                    if cmd[1] < data[1]:
                        self.userCommands[command].insert(index, data)
                        break
                else:
                    self.userCommands[command].append(data)
        for command, data in newServerCommands:
            if comand not in self.serverCommands:
                self.serverCommands[command] = [data]
            else:
                for index, cmd in enumerate(self.serverCommands[command]):
                    if cmd[1] < data[1]:
                        self.serverCommands[command].insert(index, data)
                        break
                else:
                    self.serverCommands[command].append(data)
    
    def rehash(self):
        log.msg("Rehashing...", logLevel=logging.INFO)
        self.config.reload()

class ModuleLoadError(Exception):
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc
    
    def __str__(self):
        return "Module {} could not be loaded: {}".format(name, desc)