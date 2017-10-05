from twisted.internet.protocol import ClientFactory, Factory
from txircd.server import IRCServer
from txircd.user import IRCUser
import re

ipv4MappedAddr = re.compile("::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
def unmapIPv4(ip: str) -> str:
	"""
	Converts an IPv6-mapped IPv4 address to a bare IPv4 address.
	"""
	mapped = ipv4MappedAddr.match(ip)
	if mapped:
		return mapped.group(1)
	return ip

class UserFactory(Factory):
	protocol = IRCUser
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def buildProtocol(self, addr):
		return self.protocol(self.ircd, unmapIPv4(addr.host))

class ServerListenFactory(Factory):
	protocol = IRCServer
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def buildProtocol(self, addr):
		return self.protocol(self.ircd, unmapIPv4(addr.host), True)

class ServerConnectFactory(ClientFactory):
	protocol = IRCServer
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def buildProtocol(self, addr):
		return self.protocol(self.ircd, unmapIPv4(addr.host), False)