from collections import MutableMapping
from datetime import datetime
import re

validNick = re.compile(r"^[a-zA-Z\-\[\]\\`^{}_|][a-zA-Z0-9\-\[\]\\^{}_|]*$")
def isValidNick(nick):
	"""
	Determines whether the provided nickname is in a valid format.
	"""
	return validNick.match(nick)

validHost = re.compile(r"^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*$")
def isValidHost(host):
	"""
	Determines whether the provided hostname is in a valid format.
	"""
	return validHost.match(host)

def isValidChannelName(channelName):
	"""
	Determines whether the given channel name is in a valid format.
	"""
	if channelName[0] != "#":
		return False
	for char in "\x07 ,?*": # \x07, space, and comma are explicitly denied by RFC; * and ? make matching a channel name difficult
		if char in channelName:
			return False
	return True

validMetadataKey = re.compile(r"^[A-Za-z0-9_.:]+$")
def isValidMetadataKey(key):
	"""
	Determines whether the given metadata key is in a valid format.
	"""
	return validMetadataKey.match(key)


def _enum(**enums):
	return type('Enum', (), enums)

ModeType = _enum(List=0, ParamOnUnset=1, Param=2, NoParam=3, Status=4)


def ircLower(string):
	"""
	Lowercases a string according to RFC lowercasing standards.
	"""
	return string.lower().replace("[", "{").replace("]", "}").replace("\\", "|")

class CaseInsensitiveDictionary(MutableMapping):
	"""
	It's a dictionary with RFC-case-insensitive keys.
	"""
	def __init__(self, dictType = dict):
		self._data = dictType()

	def __repr__(self):
		return repr(self._data)

	def __delitem__(self, key):
		try:
			del self._data[ircLower(key)]
		except KeyError:
			raise KeyError(key)

	def __getitem__(self, key):
		try:
			return self._data[ircLower(key)]
		except KeyError:
			raise KeyError(key)

	def __iter__(self):
		return iter(self._data)

	def __len__(self):
		return len(self._data)

	def __setitem__(self, key, value):
		self._data[ircLower(key)] = value


def now():
	"""
	Returns a datetime object representing now.
	"""
	return datetime.utcnow().replace(microsecond=0)

def timestamp(time):
	"""
	Converts a datetime object to a Unix timestamp.
	"""
	unixEpoch = datetime.utcfromtimestamp(0)
	return int((time - unixEpoch).total_seconds())

def isoTime(time):
	"""
	Converts a datetime object to an ISO-format date.
	"""
	if time.microsecond == 0:
		time = time.replace(microsecond=1) # Force milliseconds to appear
	return "{}Z".format(time.isoformat()[:-3])


def durationToSeconds(durationStr):
	"""
	Converts a 1y2w3d4h5m6s format string duration into a number of seconds.
	"""
	try: # If it's just a number, assume it's seconds.
		return int(durationStr)
	except ValueError:
		pass
	
	units = {
		"y": 31557600,
		"w": 604800,
		"d": 86400,
		"h": 3600,
		"m": 60
	}
	seconds = 0
	count = []
	for char in durationStr:
		if char.isdigit():
			count.append(char)
		else:
			if not count:
				continue
			newSeconds = int("".join(count))
			if char in units:
				newSeconds *= units[char]
			seconds += newSeconds
			count = []
	return seconds


def unescapeEndpointDescription(desc):
	"""
	Takes escaped endpoint descriptions from our configuration and unescapes
	them to pass as a Twisted endpoint description.
	"""
	result = []
	escape = []
	depth = 0
	desc = iter(desc)
	for char in desc:
		if char == "\\":
			try:
				char = desc.next()
			except StopIteration:
				raise ValueError ("Endpoint description not valid: escaped end of string")
			if char not in "{}":
				char = "\\{}".format(char)
			if depth == 0:
				result.extend(char)
			else:
				escape.extend(char)
		elif char == "{":
			if depth > 0:
				escape.append("{")
			depth += 1
		elif char == "}":
			depth -= 1
			if depth < 0:
				raise ValueError ("Endpoint description not valid: mismatched end brace")
			if depth == 0:
				result.extend(unescapeEndpointDescription("".join(escape)).replace("\\", "\\\\").replace(":", "\\:").replace("=", "\\="))
			else:
				escape.append("}")
		else:
			if depth == 0:
				result.append(char)
			else:
				escape.append(char)
	if depth != 0:
		raise ValueError ("Endpoint description not valid: mismatched opening brace")
	return "".join(result)


def splitMessage(message, maxLength, splitOnCharacter = " "):
	"""
	Split a string into a series of strings each with maximum length maxLength
	and returns them in a list.
	"""
	msgList = []
	while message:
		limitedMessage = message[:maxLength]
		if "\n" in limitedMessage:
			pos = limitedMessage.find("\n")
			newMsg = limitedMessage[:pos]
			if newMsg:
				msgList.append(newMsg)
			message = message[pos+1:] # Skip the newline
		elif limitedMessage == message:
			msgList.append(limitedMessage)
			message = ""
		elif splitOnCharacter in limitedMessage:
			pos = limitedMessage.rfind(splitOnCharacter)
			newMsg = limitedMessage[:pos]
			if newMsg:
				msgList.append(newMsg)
			message = message[pos+1:] # Skip the space
		else:
			msgList.append(limitedMessage)
			message = message[maxLength:]
	return msgList

# \x02: bold
# \x1f: underline
# \x16: reverse
# \x1d: italic
# \x0f: normal
# \x03: color stop
# \x03FF: set foreground
# \x03FF,BB: set fore/background
format_chars = re.compile('[\x02\x1f\x16\x1d\x0f]|\x03([0-9]{1,2}(,[0-9]{1,2})?)?')
def stripFormatting(message):
	"""
	Removes IRC formatting from the provided message.
	"""
	return format_chars.sub('', message)


def ipIsV4(ip):
	"""
	Checks whether an IP address is IPv4. Assumes that it's known the parameter is an IP address.
	"""
	return "." in ip

def expandIPv6Address(ip):
	if "::" in ip:
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
	return ":".join(pieces)
