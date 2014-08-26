from hashlib import md5
from twisted.internet.abstract import isIPAddress, isIPv6Address
from twisted.plugin import IPlugin
from twisted.python import log
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType
from zope.interface import implements
import logging

class HostCloaking(Mode, ModuleData):
    implements(IPlugin, IMode, IModuleData)

    name = "HostCloaking"
    affectedActions = [ "modechange-user-x" ]
    cloakingSalt = None
    cloakingPrefix = None

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def userModes(self):
        return [ ("x", ModeType.NoParam, self) ]

    def actions(self):
        return [ ("modeactioncheck-user-x-modechange-user-x", 1, self.modeChanged) ]

    def modeChanged(self, *params):
        return True

    def apply(self, actionType, user, param, settingUser, uid, adding, *params, **kw):
        if adding:
            userHost = user.host
            if isIPv6Address(userHost):
                user.changeHost(self.applyIPv6Cloak(userHost))
            elif isIPAddress(userHost):
                user.changeHost(self.applyIPv4Cloak(userHost))
            else:
                user.changeHost(self.applyHostCloak(userHost, user.ip))
        else:
            user.resetHost()

    def applyHostCloak(self, host, ip):
        # Find the last segments of the hostname.
        index = len(host[::-1].split(".", 3)[-1])
        # Cloak the first part of the host and leave the last segments alone.
        hostmask = "{}-{}{}".format(self.cloakingPrefix, md5(self.cloakingSalt + host[:index]).hexdigest()[:8], host[index:])
        # This is very rare since we only leave up to 3 segments uncloaked, but make sure the end result isn't too long.
        if len(hostmask) > 64:
            if isIPv6Address(ip):
                return self.applyIPv6Cloak(ip)
            else:
                return self.applyIPv4Cloak(ip)
        else:
            return hostmask

    def applyIPv4Cloak(self, ip):
        pieces = ip.split(".")
        hashedParts = []
        for i in range(len(pieces)):
            piecesGroup = pieces[i:]
            piecesGroup.reverse()
            hashedParts.append(md5(self.cloakingSalt + "".join(piecesGroup)).hexdigest()[:8])
        return "{}.IP".format(".".join(hashedParts))

    def applyIPv6Cloak(self, ip):
        if "::" in ip:
            # Our cloaking method relies on a fully expanded address
            count = 6 - ip.replace("::", "").count(":")
            ip = ip.replace("::", ":{}:".format(":".join(["0000" for i in range(count)])))
            if ip[0] == ":":
                ip = "0000{}".format(ip)
            if ip[-1] == ":":
                ip = "{}0000".format(ip)
        pieces = ip.split(":")
        for index, piece in enumerate(pieces):
            pieceLen = len(piece)
            if pieceLen < 4:
                pieces[index] = "{}{}".format("".join(["0" for i in range(4 - pieceLen)]), piece)
        hashedParts = []
        pieces.reverse()
        for i in range(len(pieces)):
            piecesGroup = pieces[i:]
            piecesGroup.reverse()
            hashedParts.append(md5(self.cloakingSalt + "".join(piecesGroup)).hexdigest()[:5])
        return "{}.IP".format(".".join(hashedParts))

    def load(self):
        try:
            self.cloakingSalt = self.ircd.config["cloaking_salt"]
        except KeyError:
            self.cloakingSalt = ""
            log.msg("No cloaking salt was found in the config. Host cloaks will be insecure!", logLevel=logging.WARNING)
        self.cloakingPrefix = self.ircd.config.getWithDefault("cloaking_prefix", "txircd")

    def fullUnload(self):
        for user in self.ircd.users.itervalues():
            if user.uuid[:3] == self.ircd.serverID and "x" in user.modes:
                user.setModes(self.ircd.serverID, "-x", [])

hostCloaking = HostCloaking()