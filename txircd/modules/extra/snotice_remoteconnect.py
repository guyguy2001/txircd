from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements

class SnoRemoteConnect(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "ServerNoticeRemoteConnect"
	
	def __init__(self):
		self.burstingServer = None
	
	def actions(self):
		return [ ("remoteregister", 1, self.sendRemoteConnectNotice),
		         ("servernoticetype", 1, self.checkSnoType),
		         ("startburstcommand", 1, self.markStartBurst),
		         ("endburstcommand", 1, self.markEndBurst) ]
	
	def sendRemoteConnectNotice(self, user, *params):
		server = self.ircd.servers[user.uuid[:3]].name
		if server == self.burstingServer:
			return
		message =  "Client connected on {}: {} ({}) [{}]".format(server, user.hostmaskWithRealHost(), user.ip, user.gecos)
		snodata = {
			"mask": "connect",
			"message": message
		}
		self.ircd.runActionProcessing("sendservernotice", snodata)
	
	def checkSnoType(self, user, typename):
		return typename == "remoteconnect"
	
	def markStartBurst(self, server, command):
		self.burstingServer = server
	
	def markEndBurst(self, server, command):
		self.burstingServer = None

snoRemoteConnect = SnoRemoteConnect()