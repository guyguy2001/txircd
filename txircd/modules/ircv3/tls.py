from twisted.internet.interfaces import ISSLTransport, ITLSTransport
from twisted.internet.ssl import DefaultOpenSSLContextFactory
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements
from OpenSSL import SSL

# Numerics and names are from the IRCv3.1 spec at http://ircv3.net/specs/extensions/tls-3.1.html
irc.RPL_STARTTLS = "670"
irc.ERR_STARTTLS = "691"

class StartTLS(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "StartTLS"
	forRegistered = False
	
	def actions(self):
		return [ ("capabilitylist", 10, self.addCapability) ]
	
	def userCommands(self):
		return [ ("STARTTLS", 1, self) ]
	
	def load(self):
		if "unloading-tls" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-tls"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("tls")
		self.certContext = DefaultOpenSSLContextFactory(self.ircd.config["starttls_key"], self.ircd.config["starttls_cert"])
		self.certContext.getContext().set_verify(SSL.VERIFY_PEER, lambda connection, x509, errnum, errdepth, ok: True)
	
	def unload(self):
		self.ircd.dataCache["unloading-tls"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-tls"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("tls")
	
	def verifyConfig(self, config):
		if "starttls_key" in config:
			if not isinstance(config["starttls_key"], basestring):
				raise ConfigValidationError("starttls_key", "value must be a file name")
		else:
			config["starttls_key"] = "server.pem" # We'll use the Twisted default for endpoints here
		if "starttls_cert" in config:
			if not isinstance(config["starttls_cert"], basestring):
				raise ConfigValidationError("starttls_cert", "value must be a file name")
		else:
			config["starttls_cert"] = config["starttls_key"]
	
	def addCapability(self, capList):
		capList.append("tls")
	
	def parseParams(self, user, prefix, params, tags):
		return {}
	
	def execute(self, user, data):
		if user.secureConnection:
			user.sendMessage(irc.ERR_STARTTLS, "The connection is already secure")
			return True
		try:
			secureTransport = ITLSTransport(user.transport)
		except TypeError:
			user.sendMessage(irc.ERR_STARTTLS, "Failed to initialize transport for STARTTLS")
			return True
		if secureTransport is None:
			user.sendMessage(irc.ERR_STARTTLS, "Failed to initialize transport for STARTTLS")
			return True
		user.transport = secureTransport
		user.sendMessage(irc.RPL_STARTTLS, "STARTTLS successful; proceed with TLS handshake")
		secureTransport.startTLS(self.certContext)
		user.secureConnection = ISSLTransport(secureTransport, None) is not None
		return True

startTLS = StartTLS()