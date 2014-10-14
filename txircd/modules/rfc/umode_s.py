from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ircLower, ModeType, timestamp
from zope.interface import implements
from weakref import WeakSet

irc.RPL_LISTMODE = "786" # Made up
irc.RPL_ENDOFLISTMODE = "787" # Made up
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
                ("modechange-user-s", 1, self.modeChanged),
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

    def modeChanged(self, user, source, adding, param, *params):
        if adding:
            if self.ircd.runActionUntilTrue("servernoticetype", user, param):
                if param not in self.subscribeLists:
                    self.subscribeLists[param] = WeakSet()
                if user.uuid[:3] == self.ircd.serverID:
                    self.subscribeLists[param].add(user)
            else:
                user.sendMessage(irc.ERR_INVALIDSNOTYPE, param, ":Invalid server notice type")
        else:
            if param in self.subscribeLists and user in self.subscribeLists[param]:
                self.subscribeLists[param].remove(user)

    def sendServerNotice(self, snodata):
        mask = snodata["mask"]
        if mask in self.subscribeLists:
            for u in self.subscribeLists[mask]:
                u.sendMessage("NOTICE", ":*** {}".format(snodata["message"]))

    def checkSet(self, user, param):
        return ircLower(param).split(",")

    def checkUnset(self, user, param):
        return ircLower(param).split(",")

    def showListParams(self, user, target):
        if "s" in target.modes:
            for mask in target.modes["s"]:
                target.sendMessage(irc.RPL_LISTMODE, "s", mask[0], mask[1], str(timestamp(mask[2])))
        target.sendMessage(irc.RPL_ENDOFLISTMODE, ":End of server notice type list")

snoMode = ServerNoticeMode()