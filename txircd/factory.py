from twisted.internet.protocol import ClientFactory, Factory
from txircd.server import IRCServer
from txircd.user import IRCUser
from ipaddress import ip_address
from typing import Union

def unmapIPv4(ip: str) -> Union["IPv4Address", "IPv6Address"]:
	"""
	Converts an IPv6-mapped IPv4 address to a bare IPv4 address.
	"""
	addr = ip_address(ip)
	if addr.ipv4_mapped is None:
		return addr
	return addr.ipv4_mapped

class UserFactory(Factory):
	protocol = IRCUser
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def buildProtocol(self, addr):
		return self.protocol(self.ircd, ip_address(unmapIPv4(addr.host)))

class ServerListenFactory(Factory):
	protocol = IRCServer
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def buildProtocol(self, addr):
		return self.protocol(self.ircd, ip_address(unmapIPv4(addr.host)), True)

class ServerConnectFactory(ClientFactory):
	protocol = IRCServer
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def buildProtocol(self, addr):
		return self.protocol(self.ircd, ip_address(unmapIPv4(addr.host)), False)