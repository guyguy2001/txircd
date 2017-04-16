from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements
from base64 import b64decode

class SASLPlain(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "SASLPlain"
	
	def actions(self):
		return [ ("saslmechanismlist", 10, self.addPlainToMechList),
			("startsasl", 10, self.acceptPlain),
			("authenticatesasl", 10, self.startAuth) ]
	
	def load(self):
		if "unloading-sasl-plain" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-sasl-plain"]
			return
		if "saslmech-add" in self.ircd.functionCache:
			self.ircd.functionCache["saslmech-add"]("PLAIN")
	
	def unload(self):
		self.ircd.dataCache["unloading-sasl-plain"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-sasl-plain"]
		if "saslmech-del" in self.ircd.functionCache:
			self.ircd.functionCache["saslmech-del"]("PLAIN")
	
	def addPlainToMechList(self, mechList):
		mechList.append("PLAIN")
	
	def acceptPlain(self, user, mechanism):
		if mechanism == "PLAIN":
			return True
		return False
	
	def startAuth(self, user, saslData):
		if "sasl-mech" not in user.cache or user.cache["sasl-mech"] != "PLAIN":
			return None
		plainData = b64decode(saslData)
		try:
			username, _, password = plainData.split("\0")
		except ValueError:
			return False
		result = self.ircd.runActionUntilValue("authenticatesasl-PLAIN", user, username, password)
		if result is None:
			return False
		return result

plainSASLAuth = SASLPlain()