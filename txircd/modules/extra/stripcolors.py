from twisted.plugin import IPlugin
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements
import re

class StripColors(ModuleData, Mode):
    implements(IPlugin, IModuleData, IMode)

    name = "StripColors"
    affectedActions = [ "commandmodify-PRIVMSG", "commandmodify-NOTICE" ]

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def channelModes(self):
        return [ ("S", ModeType.NoParam, self) ]

    def actions(self):
        return [ ("modeactioncheck-channel-S-commandmodify-PRIVMSG", 10, self.channelHasMode),
                ("modeactioncheck-channel-S-commandmodify-NOTICE", 10, self.channelHasMode) ]

    def channelHasMode(self, channel, user, command, data):
        if "S" in channel.modes:
            return ""
        return None

    # \x02: bold
    # \x1f: underline
    # \x16: reverse
    # \x1d: italic
    # \x0f: normal
    # \x03: color stop
    # \x03FF: set foreground
    # \x03FF,BB: set fore/background
    format_chars = re.compile('[\x02\x1f\x16\x1d\x0f]|\x03([0-9]{1,2}(,[0-9]{1,2})?)?')
    def apply(self, actionName, channel, param, user, command, data):
        minAllowedRank = self.ircd.config.getWithDefault("exempt_chanops_stripcolor", 20)
        if channel.userRank(user) < minAllowedRank and channel in data["targetchans"]:
            message = data["targetchans"][channel]
            data["targetchans"][channel] = self.format_chars.sub('', message)


stripColors = StripColors()