from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ircLower, ModeType, timestamp
from zope.interface import implements
from weakref import WeakSet

irc.RPL_LISTMODE = "728" # Made up, based on freenode's quiet lists
irc.RPL_ENDOFLISTMODE = "729" # Made up, based on freenode's quiet lists
irc.ERR_INVALIDSNOTYPE = "985" # Made up, is not used by any IRCd

class ServerNoticeMode(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)

    name = "ServerNoticeMode"
    core = True
    subscribeLists = {}

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def userModes(self):
        return [ ("s", ModeType.List, self) ]

    def actions(self):
        return [ ("modepermission-user-s", 1, self.checkModePermission),
                ("sendservernotice", 1, self.sendServerNotice) ]

    def checkModePermission(self, user, settingUser, adding, param):
        if adding:
            if self.ircd.runActionUntilValue("userhasoperpermission", user, "servernotice-all", users=[user]):
                return True
            if self.ircd.runActionUntilValue("userhasoperpermission", user, "servernotice-type-{}".format(ircLower(param)), users=[user]):
                return True
            user.sendMessage(irc.ERR_NOPRIVILEGES, ":Permission denied - You do not have the correct operator privileges")
            return False
        return None

    def sendServerNotice(self, snodata):
        mask = snodata["mask"]
        if mask in self.subscribeLists:
            for u in self.subscribeLists[mask]:
                u.sendMessage("NOTICE", ":*** {}".format(snodata["message"]))

    def checkSet(self, user, param):
        params = param.split(",")
        validparams = []
        for par in params:
            if self.ircd.runActionUntilTrue("servernoticetype", user, par):
                mask = ircLower(par)
                if mask not in self.subscribeLists:
                    self.subscribeLists[mask] = WeakSet()
                if user not in self.subscribeLists[mask] and user.uuid[:3] == self.ircd.serverID:
                    self.subscribeLists[mask].add(user)
                    validparams.append(mask)
            else:
                user.sendMessage(irc.ERR_INVALIDSNOTYPE, par, ":Invalid server notice type")
        return validparams

    def checkUnset(self, user, param):
        params = param.split(",")
        validparams = []
        for par in params:
            mask = ircLower(par)
            if mask in self.subscribeLists and user in self.subscribeLists[mask]:
                self.subscribeLists[mask].remove(user)
                validparams.append(mask)
        return validparams

    def showListParams(self, user, target):
        if "s" in target.modes:
            for mask in target.modes["s"]:
                target.sendMessage(irc.RPL_LISTMODE, "s", mask[0], mask[1], str(timestamp(mask[2])))
        target.sendMessage(irc.RPL_ENDOFLISTMODE, ":End of server notice type list")

snoMode = ServerNoticeMode()