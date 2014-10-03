from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import ircLower
from zope.interface import implements

class RExtbans(ModuleData):
    implements(IPlugin, IModuleData)

    name = "RExtbans"

    # R extbans take the following forms:
    # "R:*" Match any logged in user
    # "R:<nick>" Match the user that owns that nick (regardless of whether it is their current nick)

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def actions(self):
        return [
            ("usermatchban-R", 10, self.matchUser),
            ("user-login", 10, self.refreshUser),
            ("user-logout", 10, self.refreshUser),
        ]

    def matchUser(self, user, negated, param):
        if negated:
            return not self.matchUser(user, False, param)
        if param == "*":
            return user.cache.get("accountid", None) is not None
        return ircLower(param) in user.cache.get("ownedNicks", [])

    def refreshUser(self, user, donorID=None):
        self.ircd.runActionStandard("updateuserbancache", user)

rextbans = RExtbans()