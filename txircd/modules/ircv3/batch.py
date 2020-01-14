from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements
from txircd.ircbase import IRCBase
import random, string

class Batch(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "Batch"
	
	def actions(self):
		return [ ("startbatchsend", 10, self.startBatch),
		         ("modifyoutgoingmessage", 10, self.addBatchTag),
		         ("endbatchsend", 10, self.endBatch),
		         ("capabilitylist", 10, self.addCapability) ]
	
	def load(self):
		if "unloading-batch" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-batch"]
			return
		if "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("batch")
	
	def unload(self):
		self.ircd.dataCache["unloading-batch"] = True
	
	def fullUnload(self):
		del self.ircd.dataCache["unloading-batch"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("batch")
	
	def addCapability(self, user, capList):
		capList.append("batch")
	
	def startBatch(self, user, batchName, batchType, *batchParameters):
		if "capabilities" not in user.cache or "batch" not in user.cache["capabilities"]:
			return
		uniqueReferenceTagParts = [ random.choice(string.ascii_letters) ]
		for i in range(2, 10):
			uniqueReferenceTagParts.append(random.choice(string.ascii_letters + string.digits))
		uniqueReferenceTag = "".join(uniqueReferenceTagParts)
		IRCBase.sendMessage(user, "BATCH", "+{}".format(uniqueReferenceTag), batchType, *batchParameters)
		user.cache["currentBatch"] = uniqueReferenceTag
	
	def addBatchTag(self, user, command, args, kw):
		if "currentBatch" in user.cache:
			if "tags" in kw:
				kw["tags"]["batch"] = user.cache["currentBatch"]
			else:
				kw["tags"] = { "batch": user.cache["currentBatch"] }
	
	def endBatch(self, user, batchName, batchType, *batchParameters):
		if "currentBatch" not in user.cache:
			return
		uniqueReferenceTag = user.cache["currentBatch"]
		del user.cache["currentBatch"]
		IRCBase.sendMessage(user, "BATCH", "-{}".format(uniqueReferenceTag))

batch = Batch()