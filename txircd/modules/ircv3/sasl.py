from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.RPL_SASLSUCCESS = "903"
irc.ERR_SASLFAIL = "904"
irc.ERR_SASLTOOLONG = "905"
irc.ERR_SASLABORTED = "906"
irc.RPL_SASLMECHS = "908"

class SASL(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "SASL"
	forRegistered = None
	
	def actions(self):
		return [ ("capabilitylist", 10, self.addCapability),
		         ("saslcomplete", 1, self.completeSASL),
		         ("register", 1, self.clearSASLonRegister) ]
	
	def userCommands(self):
		return [ ("AUTHENTICATE", 1, self) ]
	
	def load(self):
		self.ircd.functionCache["saslmech-add"] = self.addSASLMech
		self.ircd.functionCache["saslmech-del"] = self.removeSASLMech
		if "unloading-sasl" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-sasl"]
			return
		saslMechanisms = self.saslMechList()
		if saslMechanisms and "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("sasl={}".format(",".join(saslMechanisms)))
	
	def unload(self):
		self.ircd.dataCache["unloading-sasl"] = True
		del self.ircd.functionCache["saslmech-add"]
		del self.ircd.functionCache["saslmech-del"]
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-sasl"]
		saslMechanisms = self.saslMechList()
		if saslMechanisms and "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("sasl")
	
	def addCapability(self, user, capList):
		saslMechanisms = self.saslMechList()
		if not saslMechanisms:
			return
		if not user or ("capversion" in user.cache and user.cache["capversion"] >= 302):
			capList.append("sasl={}".format(",".join(saslMechanisms)))
		else:
			capList.append("sasl")
	
	def completeSASL(self, user, success):
		if success:
			user.sendMessage(irc.RPL_SASLSUCCESS, "SASL authentication successful")
		else:
			user.sendMessage(irc.ERR_SASLFAIL, "SASL authentication failed")
		self.cleanup(user)
	
	def clearSASLonRegister(self, user):
		if "sasl-mech" in user.cache and "sasl-processing" not in user.cache:
			user.sendMessage(irc.ERR_SASLABORTED, "SASL authentication aborted")
			self.cleanup(user)
		return True
	
	def cleanup(self, user):
		if "sasl-mech" in user.cache:
			del user.cache["sasl-mech"]
		if "sasl-data" in user.cache:
			del user.cache["sasl-data"]
		if "sasl-processing" in user.cache:
			del user.cache["sasl-processing"]
	
	def addSASLMech(self, mechanism, notifyBatchName = None):
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("sasl={}".format(mechanism), notifyBatchName)
	
	def removeSASLMech(self, mechanism, notifyBatchName = None):
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("sasl={}".format(mechanism), notifyBatchName)
	
	def saslMechList(self):
		saslMechanisms = []
		self.ircd.runActionStandard("saslmechanismlist", saslMechanisms)
		return saslMechanisms
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 1:
			user.sendSingleError("AuthenticateParams", irc.ERR_NEEDMOREPARAMS, "AUTHENTICATE", "Not enough parameters")
			return None
		payload = params[0]
		if len(params[0]) > 400:
			user.sendSingleError("AuthenticateLength", irc.ERR_SASLTOOLONG, "SASL message too long")
			return None
		return {
			"payload": payload
		}
	
	def execute(self, user, data):
		payload = data["payload"]
		if "sasl-mech" not in user.cache:
			saslMechanisms = self.saslMechList()
			useMechanism = payload.upper()
			if useMechanism not in saslMechanisms:
				user.sendMessage(irc.RPL_SASLMECHS, ",".join(saslMechanisms), "are available SASL mechanisms")
				user.sendMessage(irc.ERR_SASLFAIL, "SASL authentication failed")
				return True
			if self.ircd.runActionUntilTrue("startsasl", user, useMechanism):
				user.cache["sasl-mech"] = useMechanism
				return True
			user.sendMessage(irc.ERR_SASLFAIL, "SASL authentication failed")
			return True
		if payload == "*":
			self.cleanup(user)
			user.sendMessage(irc.ERR_SASLABORTED, "SASL authentication aborted")
			return True
		if len(payload) == 400:
			if "sasl-data" not in user.cache:
				user.cache["sasl-data"] = payload
			else:
				user.cache["sasl-data"] += payload
			return True
		if payload != "+":
			if "sasl-data" not in user.cache:
				user.cache["sasl-data"] = payload
			else:
				user.cache["sasl-data"] += payload
		elif "sasl-data" not in user.cache:
			user.cache["sasl-data"] = ""
		
		# We run this action to authenticate users via SASL, passing the SASL data we received from the client.
		# The action returns values of the following:
		# - False (do not authenticate)
		# - None (was not processed)
		# - True (authenticated)
		# - "defer" (we're still processing the result and will let you know later by calling completeSASL as to the result)
		result = self.ircd.runActionUntilValue("authenticatesasl", user, user.cache["sasl-data"])
		if not result:
			user.sendMessage(irc.ERR_SASLFAIL, "SASL authentication failed")
		elif result != "defer":
			user.sendMessage(irc.RPL_SASLSUCCESS, "SASL authentication successful")
		return True

sasl = SASL()