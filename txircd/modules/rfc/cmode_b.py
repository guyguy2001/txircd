from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ircLower, ModeType, now, timestamp
from zope.interface import implements
from fnmatch import fnmatch

class BanMode(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)
    
    name = "BanMode"
    core = True
    affectedActions = [ "joinpermission" ]
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def channelModes(self):
        return [ ("b", ModeType.List, self) ]
    
    def actions(self):
        return [ ("modeactioncheck-channel-withuser", 100, self.checkAction),
                ("modechange-channel-b", 1, self.onChange),
                ("userbancheck", 1, self.matchBans),
                ("join", 1, self.populateBanCache),
                ("leave", 10, self.clearBanCache) ]
    
    def banMatchesUser(self, user, banmask):
        matchingExtban = ""
        matchNegated = False
        if ":" in banmask and ("@" not in banmask or banmask.find(":") < banmask.find("@")):
            matchingExtban, banmask = banmask.split(":", 1)
            if matchingExtban and matchingExtban[0] == "~":
                matchNegated = True
                matchingExtban = matchingExtban[1:]
        if matchingExtban:
            return self.ircd.runActionUntilTrue("usermatchban-{}".format(matchingExtban), user, matchNegated, banmask)
        return self.matchHostmask(user, banmask)
    
    def matchHostmask(self, user, banmask):
        banmask = ircLower(banmask)
        userMask = ircLower(user.hostmask())
        if fnmatch(userMask, banmask):
            return True
        userMask = ircLower(user.hostmaskWithRealHost())
        if fnmatch(userMask, banmask):
            return True
        userMask = ircLower(user.hostmaskWithIP())
        return fnmatch(userMask, banmask)
    
    def checkAction(self, actionName, mode, channel, user, *params, **kw):
        if "b" not in channel.modes:
            return None
        if mode == "b":
            if "b" in channel.modes:
                return "" # We'll handle the iteration
            return None
        if "bans" in user.cache and channel in user.cache["bans"]:
            if mode in user.cache["bans"][channel]:
                return user.cache["bans"][channel]
            return None
        for paramData in channel.modes["b"]:
            param = paramData[0]
            actionExtban = ""
            actionParam = ""
            matchingExtban = ""
            matchNegated = False
            if ";" in param:
                actionExtban, param = param.split(";", 1)
                if ":" in actionExtban:
                    actionExtban, actionParam = actionExtban.split(":", 1)
            if actionExtban != mode:
                continue
            match = self.banMatchesUser(user, param)
            if match:
                return actionParam
        return None
    
    def onChange(self, channel, source, adding, param):
        if ";" in param:
            actionExtban, banmask = param.split(";", 1)
            if ":" in actionExtban:
                actionExtban, actionParam = actionExtban.split(":", 1)
            else:
                actionParam = ""
        else:
            actionExtban= ""
            actionParam = ""
            banmask = param
        if ":" in banmask and ("@" not in banmask or banmask.index(":") < banmask.index("@")):
            matchingExtban, banmask = banmask.split(":", 1)
            if matchingExtban and matchingExtban[0] == "~":
                matchNegated = True
                matchingExtban = matchingExtban[1:]
            else:
                matchNegated = False
        else:
            matchingExtban = ""
            matchNegated = None
        for user in channel.users:
            if "bans" not in user.cache:
                user.cache["bans"] = {}
            if channel not in user.cache["bans"]:
                user.cache["bans"][channel] = {}
            if (actionExtban in user.cache["bans"][channel]) == adding:
                continue # If it didn't affect them before, it won't now, so let's skip the mongo processing we're about to do to them
            if matchingExtban:
                matchesUser = self.ircd.runActionUntilTrue("usermatchban-{}".format(matchingExtban), user, matchNegated, banmask)
            else:
                matchesUser = self.matchHostmask(user, banmask)
            if not matchesUser:
                continue
            if adding:
                user.cache["bans"][channel][actionExtban] = actionParam
            else:
                del user.cache["bans"][channel][actionExtban]
    
    def matchBans(self, user, channel):
        if user in channel.users and "bans" in user.cache and channel in user.cache["bans"]:
            return user.cache["bans"][channel]
        matchedActions = {}
        if "b" in channel.modes:
            matchesActions = {}
            for paramData in channel.modes["b"]:
                param = paramData[0]
                actionExtban = ""
                actionParam = ""
                matchingExtban = ""
                matchNegated = False
                if ";" in param:
                    actionExtban, param = param.split(";", 1)
                    if ":" in actionExtban:
                        actionExtban, actionParam = actionExtban.split(":", 1)
                if actionExtban in matchesActions:
                    continue
                if ":" in param and ("@" not in param or param.find(":") < param.find("@")):
                    matchingExtban, param = param.split(":", 1)
                    if matchingExtban[0] == "~":
                        matchNegated = True
                        matchingExtban = matchingExtban[1:]
                if matchingExtban:
                    if self.ircd.runActionUntilTrue("usermatchban-{}".format(matchingExtban), user, matchNegated, param):
                        matchesActions[actionExtban] = actionParam
                else:
                    if self.matchHostmask(user, param):
                        matchesActions[""] = ""
            return matchesActions
        return {}
    
    def populateBanCache(self, channel, user):
        if "b" not in channel.modes:
            return
        if "bans" not in user.cache:
            user.cache["bans"] = {}
        user.cache["bans"][channel] = {}
        for paramData in channel.modes["b"]:
            param = paramData[0]
            actionExtban = ""
            actionParam = ""
            matchingExtban = ""
            if ";" in param:
                actionExtban, param = param.split(";", 1)
                if ":" in actionExtban:
                    actionExtban, actionParam = actionExtban.split(":", 1)
            if actionExtban in user.cache["bans"][channel]:
                continue
            if self.banMatchesUser(user, param):
                user.cache["bans"][channel][actionExtban] = actionParam
    
    def clearBanCache(self, channel, user):
        if "bans" in user.cache and channel in user.cache["bans"]:
            del user.cache["bans"][channel]
    
    def checkSet(self, channel, param):
        actionExtban = ""
        actionParam = ""
        matchingExtban = ""
        banmask = param
        if ";" in banmask:
            actionExtban, banmask = banmask.split(";", 1)
            if not actionExtban or not banmask:
                return []
            if ":" in actionExtban:
                actionExtban, actionParam = actionExtban.split(":", 1)
                if not actionParam:
                    return []
            if actionExtban not in self.ircd.channelModeTypes:
                return None
            actionModeType = self.ircd.channelModeTypes[actionExtban]
            if actionModeType == ModeType.List or actionModeType == ModeType.Status:
                return []
            if actionParam and actionModeType == ModeType.NoParam:
                return []
            if not actionParam and actionModeType in (ModeType.ParamOnUnset, ModeType.Param):
                return []
        if ":" in banmask and ("@" not in banmask or banmask.find(":") < banmask.find("@")):
            matchingExtban, banmask = banmask.split(":", 1)
            if not matchingExtban:
                return []
        else:
            if "!" not in banmask:
                param += "!*@*" # Append it to the param since it needs to go to output (and banmask is at the trailing end of param so it's OK)
            elif "@" not in banmask:
                param += "@*"
        return [param]
    
    def checkUnset(self, channel, param):
        actionExtban = ""
        banmask = param
        if ";" in banmask:
            actionExtban, banmask = banmask.split(";", 1)
            # We don't care about the rest of actionExtban here
        if ":" in banmask and ("@" not in banmask or banmask.find(":") < banmask.find("@")):
            return [param] # Just let it go; the other checks will be managed by checking whether the parameter is actually set on the channel
        # If there's no matching extban, make sure the ident and host are given
        if "!" not in banmask:
            return ["{}!*@*".format(param)]
        if "@" not in banmask:
            return ["{}@*".format(param)]
        return [param]
    
    def apply(self, actionType, channel, param, actionChannel, user): # We spell the parameters out because the only action we accept is joinpermission
        # When we get in this function, the user is trying to join, so the cache will always either not exist or be invalid
        # so we'll go straight to analyzing the ban list
        if "b" not in channel.modes:
            return None
        for paramData in channel.modes["b"]:
            param = paramData[0]
            if ";" in param:
                continue # Ignore entries with action extbans
            if self.banMatchesUser(user, param):
                return False
        return None
    
    def showListParams(self, user, channel):
        if user not in channel.users or "b" not in channel.modes:
            user.sendMessage(irc.RPL_ENDOFBANLIST, channel.name, ":End of channel ban list")
            return
        for paramData in channel.modes["b"]:
            user.sendMessage(irc.RPL_BANLIST, channel.name, paramData[0], paramData[1], str(timestamp(paramData[2])))
        user.sendMessage(irc.RPL_ENDOFBANLIST, channel.name, ":End of channel ban list")

banMode = BanMode()