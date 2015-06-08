from twisted.internet.abstract import isIPAddress, isIPv6Address
from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IMode, IModuleData, Mode, ModuleData
from txircd.utils import isValidHost, ModeType
from zope.interface import implements
from hashlib import sha256

class HostCloaking(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)

	name = "HostCloaking"
	affectedActions = { "modechange-user-x": 10 }
	cloakingSalt = None
	cloakingPrefix = None

	def userModes(self):
		return [ ("x", ModeType.NoParam, self) ]

	def actions(self):
		return [ ("modeactioncheck-user-x-modechange-user-x", 1, self.modeChanged) ]

	def verifyConfig(self, config):
		if "cloaking_salt" in config:
			if not isinstance(config["cloaking_salt"], basestring):
				raise ConfigValidationError("cloaking_salt", "value must be a string")
			if not config["cloaking_salt"]:
				self.ircd.log.warn("No cloaking salt was found in the config. Host cloaks will be insecure!")
		else:
			self.ircd.log.warn("No cloaking salt was found in the config. Host cloaks will be insecure!")
		if "cloaking_prefix" in config and not isValidHost(config["cloaking_prefix"]): # Make sure the prefix will not make the cloak an invalid hostname
			raise ConfigValidationError("cloaking_prefix", "value must be a string and must not contain any invalid hostname characters")

	def modeChanged(self, user, *params):
		if user.uuid[:3] == self.ircd.serverID:
			return True
		return None

	def apply(self, actionType, user, param, settingUser, uid, adding, *params, **kw):
		if adding:
			userHost = user.realHost
			if isIPv6Address(userHost):
				user.changeHost(self.applyIPv6Cloak(userHost))
			elif isIPAddress(userHost):
				user.changeHost(self.applyIPv4Cloak(userHost))
			else:
				if "." in userHost:
					user.changeHost(self.applyHostCloak(userHost, user.ip))
				else:
					if isIPv6Address(user.ip):
						return self.applyIPv6Cloak(user.ip)
					else:
						return self.applyIPv4Cloak(user.ip)
		else:
			user.resetHost()

	def applyHostCloak(self, host, ip):
		# Find the last segments of the hostname.
		index = len(host[::-1].split(".", 3)[-1])
		# Cloak the first part of the host and leave the last segments alone.
		hostmask = "{}-{}{}".format(self.ircd.config.get("cloaking_prefix", "txircd"), sha256(self.ircd.config.get("cloaking_salt", "") + host[:index]).hexdigest()[:8], host[index:])
		# This is very rare since we only leave up to 3 segments uncloaked, but make sure the end result isn't too long.
		if len(hostmask) > self.ircd.config.get("hostname_length", 64):
			if isIPv6Address(ip):
				return self.applyIPv6Cloak(ip)
			else:
				return self.applyIPv4Cloak(ip)
		else:
			return hostmask

	def applyIPv4Cloak(self, ip):
		pieces = ip.split(".")
		hashedParts = []
		for i in range(len(pieces), 0, -1):
			piecesGroup = pieces[:i]
			piecesGroup.reverse()
			hashedParts.append(sha256(self.ircd.config.get("cloaking_salt", "") + "".join(piecesGroup)).hexdigest()[:8])
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
		for i in range(len(pieces), 0, -1):
			piecesGroup = pieces[:i]
			piecesGroup.reverse()
			hashedParts.append(sha256(self.ircd.config.get("cloaking_salt", "") + "".join(piecesGroup)).hexdigest()[:5])
		return "{}.IP".format(".".join(hashedParts))

hostCloaking = HostCloaking()