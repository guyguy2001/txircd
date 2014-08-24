from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import DeferredList
from twisted.internet.endpoints import clientFromString, serverFromString
from twisted.internet.task import LoopingCall
from twisted.plugin import getPlugins
from twisted.python import log
from txircd.config import Config
from txircd.factory import ServerConnectFactory, ServerListenFactory, UserFactory
from txircd.module_interface import ICommand, IMode, IModuleData
from txircd.utils import CaseInsensitiveDictionary, ModeType, now, unescapeEndpointDescription
import logging, shelve, txircd.modules

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
        self.channelStatusOrder = []
        self.channelModeTypes = {}
        self.userModes = ({}, {}, {}, {})
        self.userModeTypes = {}
        self.actions = {}
        self.storage = None
        self.storage_syncer = None
        self.dataCache = {}
        self.functionCache = {}
        
        self.serverID = None
        self.name = None
        self.isupport_tokens = {
            "CHANNELLEN": 64,
            "CASEMAPPING": "rfc1459",
            "MODES": 20,
            "NICKLEN": 32,
            "TOPICLEN": 328
        }
        self._uid = self._genUID()
        
        self.users = {}
        self.userNicks = CaseInsensitiveDictionary()
        self.channels = CaseInsensitiveDictionary()
        self.servers = {}
        self.serverNames = CaseInsensitiveDictionary()
        
        self.startupTime = None
    
    def startService(self):
        log.msg("Starting up...", logLevel=logging.INFO)
        self.startupTime = now()
        log.msg("Loading configuration...", logLevel=logging.INFO)
        self.config.reload()
        self.name = self.config["server_name"][:64]
        if "." not in self.name:
            raise ValueError ("Server name must look like a domain name")
        self.serverID = self.config["server_id"].upper()
        if len(self.serverID) != 3 or not self.serverID.isalnum() or not self.serverID[0].isdigit():
            raise ValueError ("The server ID must be a 3-character alphanumeric string starting with a number.")
        log.msg("Loading storage...", logLevel=logging.INFO)
        self.storage = shelve.open("data.db", writeback=True)
        self.storage_syncer = LoopingCall(self.storage.sync)
        self.storage_syncer.start(self.config.getWithDefault("storage_sync_interval", 5), now=False)
        log.msg("Loading modules...", logLevel=logging.INFO)
        self._loadModules()
        log.msg("Binding ports...", logLevel=logging.INFO)
        self._bindPorts()
        log.msg("txircd started!", logLevel=logging.INFO)
        self.runActionStandard("startup")
    
    def stopService(self):
        stopDeferreds = []
        log.msg("Disconnecting servers...", logLevel=logging.INFO)
        serverList = self.servers.values() # Take the list of server objects
        self.servers = {} # And then destroy the server dict to inhibit server objects generating lots of noise
        for server in serverList:
            if server.nextClosest == self.serverID:
                stopDeferreds.append(server.disconnectedDeferred)
                allUsers = self.users.keys()
                for user in allUsers:
                    if user[:3] == server.serverID:
                        del self.users[user]
                server.transport.loseConnection()
        log.msg("Disconnecting users...", logLevel=logging.INFO)
        userList = self.users.values() # Basically do the same thing I just did with the servers
        self.users = {}
        for user in userList:
            if user.transport:
                stopDeferreds.append(user.disconnectedDeferred)
                user.transport.loseConnection()
        log.msg("Unloading modules...", logLevel=logging.INFO)
        moduleList = self.loadedModules.keys()
        for module in moduleList:
            self.unloadModule(module, False) # Incomplete unload is done to save time and because side effects are destroyed anyway
        log.msg("Closing data storage...", logLevel=logging.INFO)
        if self.storage_syncer.running:
            self.storage_syncer.stop()
        self.storage.close() # a close() will sync() also
        log.msg("Releasing ports...", logLevel=logging.INFO)
        stopDeferreds.extend(self._unbindPorts())
        return DeferredList(stopDeferreds)
    
    def _loadModules(self):
        for module in getPlugins(IModuleData, txircd.modules):
            if module.name in self.loadedModules:
                continue
            if module.core or module.name in self.config["modules"]:
                self._loadModuleData(module)
        for moduleName in self.config["modules"]:
            if moduleName not in self.loadedModules:
                log.msg("The module {} failed to load.".format(moduleName), logLevel=logging.WARNING)
    
    def loadModule(self, moduleName):
        for module in getPlugins(IModuleData, txircd.modules):
            if module.name == moduleName:
                self._loadModuleData(module)
                break
    
    def _loadModuleData(self, module):
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
        newActions = {}
        newUserCommands = {}
        newServerCommands = {}
        common = False
        for mode in moduleData["channelmodes"]:
            if mode[0] in self.channelModeTypes:
                raise ModuleLoadError (module.name, "Tries to implement channel mode +{} when that mode is already implemented.".format(mode[0]))
            if not IMode.providedBy(mode[2]):
                raise ModuleLoadError (module.name, "Returns a channel mode object (+{}) that doesn't implement IMode.".format(mode[0]))
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
            if not IMode.providedBy(mode[2]):
                raise ModuleLoadError (module.name, "Returns a user mode object (+{}) that doesn't implement IMode.".format(mode[0]))
            newUserModes[mode[1]][mode[0]] = mode[2]
            common = True
        for action in moduleData["actions"]:
            if action[0] not in newActions:
                newActions[action[0]] = [(action[2], action[1])]
            else:
                newActions[action[0]].append((action[2], action[1]))
        for command in moduleData["usercommands"]:
            if not ICommand.providedBy(command[2]):
                raise ModuleLoadError (module.name, "Returns a user command object ({}) that doesn't implement ICommand.".format(command[0]))
            if command[0] not in newUserCommands:
                newUserCommands[command[0]] = []
            newUserCommands[command[0]].append((command[2], command[1]))
        for command in moduleData["servercommands"]:
            if not ICommand.providedBy(command[2]):
                raise ModuleLoadError (module.name, "Returns a server command object ({}) that doesnt implement ICommand.".format(command[0]))
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
        
        self.runActionStandard("moduleload", module.name)
        module.load()
        
        for type, typeSet in enumerate(newChannelModes):
            for mode, implementation in typeSet.iteritems():
                self.channelModeTypes[mode] = type
                self.channelModes[type][mode] = implementation
        for mode, data in newChannelStatuses.iteritems():
            self.channelModeTypes[mode] = ModeType.Status
            self.channelStatuses[mode] = data
            self.channelStatusSymbols[data[0]] = mode
            for index, status in enumerate(self.channelStatusOrder):
                if self.channelStatuses[status][1] < data[1]:
                    self.channelStatusOrder.insert(index, mode)
                    break
            else:
                self.channelStatusOrder.append(mode)
        for type, typeSet in enumerate(newUserModes):
            for mode, implementation in typeSet.iteritems():
                self.userModeTypes[mode] = type
                self.userModes[type][mode] = implementation
        for action, actionList in newActions.iteritems():
            if action not in self.actions:
                self.actions[action] = []
            for actionData in actionList:
                for index, handlerData in enumerate(self.actions[action]):
                    if handlerData[1] < actionData[1]:
                        self.actions[action].insert(index, actionData)
                        break
                else:
                    self.actions[action].append(actionData)
        for command, dataList in newUserCommands.iteritems():
            if command not in self.userCommands:
                self.userCommands[command] = []
            for data in dataList:
                for index, cmd in enumerate(self.userCommands[command]):
                    if cmd[1] < data[1]:
                        self.userCommands[command].insert(index, data)
                        break
                else:
                    self.userCommands[command].append(data)
        for command, dataList in newServerCommands.iteritems():
            if command not in self.serverCommands:
                self.serverCommands[command] = []
            for data in dataList:
                for index, cmd in enumerate(self.serverCommands[command]):
                    if cmd[1] < data[1]:
                        self.serverCommands[command].insert(index, data)
                        break
                else:
                    self.serverCommands[command].append(data)
    
    def unloadModule(self, moduleName, fullUnload = True):
        unloadDeferreds = []
        if moduleName not in self.loadedModules:
            return
        module = self.loadedModules[moduleName]
        if fullUnload and module.core:
            raise ValueError ("The module you're trying to unload is a core module.")
        moduleData = self._loadedModuleData[moduleName]
        d = module.unload()
        if d is not None:
            unloadDeferreds.append(d)
        
        for modeData in moduleData["channelmodes"]:
            if modeData[1] == ModeType.Status:
                del self.channelStatuses[modeData[0]]
                del self.channelStatusSymbols[modeData[4]]
                self.channelStatusOrder.remove(modeData[0])
            else:
                del self.channelModes[modeData[1]][modeData[0]]
            del self.channelModeTypes[modeData[0]]
        for modeData in moduleData["usermodes"]:
            del self.userModes[modeData[1]][modeData[0]]
            del self.userModeTypes[modeData[0]]
        for actionData in moduleData["actions"]:
            self.actions[actionData[0]].remove((actionData[2], actionData[1]))
        for commandData in moduleData["usercommands"]:
            self.userCommands[commandData[0]].remove((commandData[2], commandData[1]))
        for commandData in moduleData["servercommands"]:
            self.serverCommands[commandData[0]].remove((commandData[2], commandData[1]))
        
        if fullUnload:
            d = module.fullUnload()
            if d is not None:
                unloadDeferreds.append(d)
        del self.loadedModules[moduleName]
        del self._loadedModuleData[moduleName]
        
        self.runActionStandard("moduleunload", module.name)
        
        if unloadDeferreds:
            return DeferredList(unloadDeferreds)
    
    def reloadModule(self, moduleName):
        d = self.unloadModule(moduleName, False)
        if d is None:
            self.loadModule(moduleName)
        else:
            d.addCallback(lambda result: self.loadModule(moduleName))
    
    def rehash(self):
        log.msg("Rehashing...", logLevel=logging.INFO)
        self.config.reload()
        d = self._unbindPorts() # Unbind the ports that are bound
        if d: # And then bind the new ones
            DeferredList(d).addCallback(lambda result: self._bindPorts())
        else:
            self._bindPorts()
        for module in self.loadedModules.itervalues(): # Tell modules about it
            module.rehash()
    
    def _bindPorts(self):
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
    
    def _unbindPorts(self):
        deferreds = []
        for port in self.boundPorts.itervalues():
            d = port.stopListening()
            if d:
                deferreds.append(d)
        return deferreds
    
    def _savePort(self, port, desc):
        self.boundPorts[desc] = port
    
    def _logNotBound(self, err, desc):
        log.msg("Could not bind '{}': {}".format(desc, err), logLevel=logging.ERROR)
    
    def createUUID(self):
        newUUID = self.serverID + self._uid.next()
        while newUUID in self.users: # It'll take over 1.5 billion connections to loop around, but we still
            newUUID = self.serverID + self._uid.next() # want to be extra safe and avoid collisions
        return newUUID
    
    def _genUID(self):
        uid = "AAAAAA"
        while True:
            yield uid
            uid = self._incrementUID(uid)
    
    def _incrementUID(self, uid):
        if uid == "Z": # The first character must be a letter
            return "A" # So wrap that around
        if uid[-1] == "9":
            return self._incrementUID(uid[:-1]) + "A"
        if uid[-1] == "Z":
            return uid[:-1] + "0"
        return uid[:-1] + chr(ord(uid[-1]) + 1)
    
    def generateISupportList(self):
        isupport = self.isupport_tokens.copy()
        statusSymbolOrder = "".join([self.channelStatuses[status][0] for status in self.channelStatusOrder])
        isupport["CHANMODES"] = ",".join(["".join(modes) for modes in self.channelModes])
        isupport["PREFIX"] = "({}){}".format("".join(self.channelStatusOrder), statusSymbolOrder)
        isupport["STATUSMSG"] = statusSymbolOrder
        isupport["USERMODES"] = ",".join(["".join(modes) for modes in self.userModes])
        isupport["NETWORK"] = self.config["network_name"]
        isupportList = []
        for key, val in isupport.iteritems():
            if val is None:
                isupportList.append(key)
            else:
                isupportList.append("{}={}".format(key, val))
        return isupportList
    
    def connectServer(self, name):
        if name in self.serverNames:
            return None
        if name not in self.config.getWithDefault("links", {}):
            return None
        serverConfig = self.config["links"][name]
        if "connect_descriptor" not in serverConfig:
            return None
        endpoint = clientFromString(reactor, unescapeEndpointDescription(serverConfig["connect_descriptor"]))
        d = endpoint.connect(ServerConnectFactory(self))
        d.addCallback(self._completeServerConnection, name)
        return d
    
    def _completeServerConnection(self, result, name):
        log.msg("Connected to server {}".format(name), logLevel=logging.INFO)
        self.runActionStandard("initiateserverconnection", result)
    
    def _getActionModes(self, actionName, kw, *params):
        users = []
        channels = []
        if "users" in kw:
            users = kw["users"]
            del kw["users"]
        if "channels" in kw:
            channels = kw["channels"]
            del kw["channels"]
        
        # Python is dumb and doesn't capture variables in lambdas properly
        # So we have to force static capture by wrapping the lambdas
        checkGenericAction = "modeactioncheck-user-{}".format(actionName)
        checkGenericWithAction = "modeactioncheck-user-withchannel-{}".format(actionName)
        userApplyModes = {}
        if users:
            for modeType in self.userModes:
                for mode, modeClass in modeType.iteritems():
                    if actionName not in modeClass.affectedActions:
                        continue
                    actionList = []
                    if "modeactioncheck-user" in self.actions:
                        for action in self.actions["modeactioncheck-user"]:
                            actionList.append(((lambda action, actionName, mode: lambda user, *params, **kw: action[0](actionName, mode, user, *params, **kw))(action, actionName, mode), action[1]))
                    if "modeactioncheck-user-withchannel" in self.actions:
                        for action in self.actions["modeactioncheck-user-withchannel"]:
                            for channel in channels:
                                actionList.append(((lambda action, actionName, mode, channel: lambda user, *params, **kw: action[0](actionName, mode, user, channel, *params, **kw))(action, actionName, mode, channel), action[1]))
                    if checkGenericAction in self.actions:
                        for action in self.actions[checkGenericAction]:
                            actionList.append(((lambda action, mode: lambda user, *params, **kw: action[0](mode, user, *params, **kw))(action, mode), action[1]))
                    if checkGenericWithAction in self.actions:
                        for action in self.actions[checkGenericWithAction]:
                            for channel in channels:
                                actionList.append(((lambda action, mode, channel: lambda user, *params, **kw: action[0](mode, user, channel, *params, **kw))(action, mode, channel), action[1]))
                    checkWithAction = "modeactioncheck-user-withchannel-{}-{}".format(mode, actionName)
                    if checkWithAction in self.actions:
                        for action in self.actions[checkWithAction]:
                            for channel in channels:
                                actionList.append(((lambda action, channel: lambda user, *params, **kw: action[0](user, channel, *params, **kw))(action, channel), action[1]))
                    checkAction = "modeactioncheck-user-{}-{}".format(mode, actionName)
                    actionList = sorted((self.actions[checkAction] if checkAction in self.actions else []) + actionList, key=lambda action: action[1], reverse=True)
                    applyUsers = []
                    for user in users:
                        for action in actionList:
                            param = action[0](user, *params, **kw)
                            if param is not None:
                                if param is not False:
                                    applyUsers.append((user, param))
                                break
                    if applyUsers:
                        userApplyModes[modeClass] = applyUsers
        checkGenericAction = "modeactioncheck-channel-{}".format(actionName)
        checkGenericWithAction = "modeactioncheck-channel-withuser-{}".format(actionName)
        channelApplyModes = {}
        if channels:
            for modeType in self.channelModes:
                for mode, modeClass in modeType.iteritems():
                    if actionName not in modeClass.affectedActions:
                        continue
                    actionList = []
                    if "modeactioncheck-channel" in self.actions:
                        for action in self.actions["modeactioncheck-channel"]:
                            actionList.append(((lambda action, actionName, mode: lambda channel, *params, **kw: action[0](actionName, mode, channel, *params, **kw))(action, actionName, mode), action[1]))
                    if "modeactioncheck-channel-withuser" in self.actions:
                        for action in self.actions["modeactioncheck-channel-withuser"]:
                            for user in users:
                                actionList.append(((lambda action, actionName, mode, user: lambda channel, *params, **kw: action[0](actionName, mode, channel, user, *params, **kw))(action, actionName, mode, user), action[1]))
                    if checkGenericAction in self.actions:
                        for action in self.actions[checkGenericAction]:
                            actionList.append(((lambda action, mode: lambda channel, *params, **kw: action[0](mode, channel, *params, **kw))(action, mode), action[1]))
                    if checkGenericWithAction in self.actions:
                        for action in self.actions[checkGenericWithAction]:
                            for user in users:
                                actionList.append(((lambda action, mode, user: lambda channel, *params, **kw: action[0](mode, channel, user, *params, **kw))(action, mode, user), action[1]))
                    checkWithAction = "modeactioncheck-channel-withuser-{}-{}".format(mode, actionName)
                    if checkWithAction in self.actions:
                        for action in self.actions[checkWithAction]:
                            for user in users:
                                actionList.append(((lambda action, user: lambda channel, *params, **kw: action[0](channel, user, *params, **kw))(action, user), action[1]))
                    checkAction = "modeactioncheck-channel-{}-{}".format(mode, actionName)
                    actionList = sorted((self.actions[checkAction] if checkAction in self.actions else []) + actionList, key=lambda action: action[1], reverse=True)
                    applyChannels = []
                    for channel in channels:
                        for action in actionList:
                            param = action[0](channel, *params, **kw)
                            if param is not None:
                                if param is not False:
                                    applyChannels.append((channel, param))
                                break
                    if applyChannels:
                        channelApplyModes[modeClass] = applyChannels
        return userApplyModes, channelApplyModes
    
    def runActionStandard(self, actionName, *params, **kw):
        actionsHighPriority = []
        actionList = []
        if actionName in self.actions:
            for action in self.actions[actionName]:
                if action[1] >= 100:
                    actionsHighPriority.append(action)
                else:
                    break
            actionList = self.actions[actionName][len(actionsHighPriority):]
        userModes, channelModes = self._getActionModes(actionName, kw, *params)
        for action in actionsHighPriority:
            action[0](*params, **kw)
        for mode, users in userModes.iteritems():
            for user, param in users:
                mode.apply(actionName, user, param, *params, **kw)
        for mode, channels in channelModes.iteritems():
            for channel, param in channels:
                mode.apply(actionName, channel, param, *params, **kw)
        for action in actionList:
            action[0](*params, **kw)
    
    def runActionUntilTrue(self, actionName, *params, **kw):
        actionsHighPriority = []
        actionList = []
        if actionName in self.actions:
            for action in self.actions[actionName]:
                if action[1] >= 100:
                    actionsHighPriority.append(action)
                else:
                    break
            actionList = self.actions[actionName][len(actionsHighPriority):]
        userModes, channelModes = self._getActionModes(actionName, kw, *params)
        for action in actionsHighPriority:
            if action[0](*params, **kw):
                return True
        for mode, users in userModes.iteritems():
            for user, param in users:
                if mode.apply(actionName, user, param, *params, **kw):
                    return True
        for mode, channels in channelModes.iteritems():
            for channel, param in channels:
                if mode.apply(actionName, channel, param, *params, **kw):
                    return True
        for action in actionList:
            if action[0](*params, **kw):
                return True
        return False
    
    def runActionUntilFalse(self, actionName, *params, **kw):
        actionsHighPriority = []
        actionList = []
        if actionName in self.actions:
            for action in self.actions[actionName]:
                if action[1] >= 100:
                    actionsHighPriority.append(action)
                else:
                    break
            actionList = self.actions[actionName][len(actionsHighPriority):]
        userModes, channelModes = self._getActionModes(actionName, kw, *params)
        for action in actionsHighPriority:
            if not action[0](*params, **kw):
                return True
        for mode, users in userModes.iteritems():
            for user, param in users:
                if not mode.apply(actionName, user, param, *params, **kw):
                    return True
        for mode, channels in channelModes.iteritems():
            for channel, param in channels:
                if not mode.apply(actionName, channel, param, *params, **kw):
                    return True
        for action in actionList:
            if not action[0](*params, **kw):
                return True
        return False
    
    def runActionUntilValue(self, actionName, *params, **kw):
        actionsHighPriority = []
        actionList = []
        if actionName in self.actions:
            for action in self.actions[actionName]:
                if action[1] >= 100:
                    actionsHighPriority.append(action)
                else:
                    break
            actionList = self.actions[actionName][len(actionsHighPriority):]
        userModes, channelModes = self._getActionModes(actionName, kw, *params)
        for action in actionsHighPriority:
            value = action[0](*params, **kw)
            if value is not None:
                return value
        for mode, users in userModes.iteritems():
            for user, param in users:
                value = mode.apply(actionName, user, param, *params, **kw)
                if value is not None:
                    return value
        for mode, channels in channelModes.iteritems():
            for channel, param in channels:
                value = mode.apply(actionName, channel, param, *params, **kw)
                if value is not None:
                    return value
        for action in actionList:
            value = action[0](*params, **kw)
            if value is not None:
                return value
        return None
    
    def runActionFlagTrue(self, actionName, *params, **kw):
        oneIsTrue = False
        actionsHighPriority = []
        actionList = []
        if actionName in self.actions:
            for action in self.actions[actionName]:
                if action[1] >= 100:
                    actionsHighPriority.append(action)
                else:
                    break
            actionList = self.actions[actionName][len(actionsHighPriority):]
        userModes, channelModes = self._getActionModes(actionName, kw, *params)
        for action in actionsHighPriority:
            if action[0](*params, **kw):
                oneIsTrue = True
        for mode, users in userModes.iteritems():
            for user, param in users:
                if mode.apply(actionName, user, param, *params, **kw):
                    oneIsTrue = True
        for mode, channels in channelModes.iteritems():
            for channel, param in channels:
                if mode.apply(actionName, channel, param, *params, **kw):
                    oneIsTrue = True
        for action in actionList:
            if action[0](*params, **kw):
                oneIsTrue = True
        return oneIsTrue
    
    def runActionFlagFalse(self, actionName, *params, **kw):
        oneIsFalse = False
        actionsHighPriority = []
        actionList = []
        if actionName in self.actions:
            for action in self.actions[actionName]:
                if action[1] >= 100:
                    actionsHighPriority.append(action)
                else:
                    break
            actionList = self.actions[actionName][len(actionsHighPriority):]
        userModes, channelModes = self._getActionModes(actionName, kw, *params)
        for action in actionsHighPriority:
            if not action[0](*params, **kw):
                oneIsFalse = True
        for mode, users in userModes.iteritems():
            for user, param in users:
                if not mode.apply(actionName, user, param, *params, **kw):
                    oneIsFalse = True
        for mode, channels in channelModes.iteritems():
            for channel, param in channels:
                if not mode.apply(actionName, channel, param, *params, **kw):
                    oneIsFalse = True
        for action in actionList:
            if not action[0](*params, **kw):
                oneIsFalse = True
        return oneIsFalse
    
    def runActionProcessing(self, actionName, data, *params, **kw):
        actionsHighPriority = []
        actionList = []
        if actionName in self.actions:
            for action in self.actions[actionName]:
                if action[1] >= 100:
                    actionsHighPriority.append(action)
                else:
                    break
            actionList = self.actions[actionName][len(actionsHighPriority):]
        userModes, channelModes = self._getActionModes(actionName, kw, data, *params)
        for action in actionsHighPriority:
            action[0](data, *params, **kw)
            if not data:
                return
        for mode, users in userModes.iteritems():
            for user, param in users:
                mode.apply(actionName, user, param, data, *params, **kw)
                if not data:
                    return
        for mode, channels in channelModes.iteritems():
            for channel, param in channels:
                mode.apply(actionName, channel, param, data, *params, **kw)
                if not data:
                    return
        for action in actionList:
            action[0](data, *params, **kw)
            if not data:
                return
    
    def runActionProcessingMultiple(self, actionName, dataList, *params, **kw):
        paramList = dataList + params
        actionsHighPriority = []
        actionList = []
        if actionName in self.actions:
            for action in self.actions[actionName]:
                if action[1] >= 100:
                    actionsHighPriority.append(action)
                else:
                    break
            actionList = self.actions[actionName][len(actionsHighPriority):]
        userModes, channelModes = self._getActionModes(actionName, kw, *paramList)
        for action in actionsHighPriority:
            action[0](*paramList, **kw)
            for data in dataList:
                if data:
                    break
            else:
                return
        for mode, users in userModes.iteritems():
            for user, param in users:
                mode.apply(actionName, user, param, *paramList, **kw)
                for data in dataList:
                    if data:
                        break
                else:
                    return
        for mode, channels in channelModes.iteritems():
            for channel, param in channels:
                mode.apply(actionName, channel, param, *paramList, **kw)
                for data in dataList:
                    if data:
                        break
                else:
                    return
        for action in actionList:
            action[0](*paramList, **kw)
            for data in dataList:
                if data:
                    break
            else:
                return

class ModuleLoadError(Exception):
    def __init__(self, name, desc):
        self.message = "Module {} could not be loaded: {}".format(name, desc)