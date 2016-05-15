from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class ErrorResponse(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ErrorResponse"
	core = True
	
	def actions(self):
		return [ ("quit", 10, self.sendError) ]
	
	def sendError(self, user, reason, fromServer):
		user.sendMessage("ERROR", "Closing Link: {}@{} [{}]".format(user.ident, user.host(), reason), to=None, prefix=None)

errorResponse = ErrorResponse()