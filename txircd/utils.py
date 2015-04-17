from collections import MutableMapping
from datetime import datetime
import re

validNick = re.compile(r"^[a-zA-Z\-\[\]\\`^{}_|][a-zA-Z0-9\-\[\]\\1^{}_|]{0,31}$")
def isValidNick(nick):
	return validNick.match(nick)

validHost = re.compile(r"^[a-zA-Z0-9.-]+$")
def isValidHost(host):
	return validHost.match(host)

def isValidChannelName(channelName):
	if channelName[0] != "#":
		return False
	for char in "\x07 ,?*": # \x07, space, and comma are explicitly denied by RFC; * and ? make matching a channel name difficult
		if char in channelName:
			return False
	return True


def _enum(**enums):
	return type('Enum', (), enums)

ModeType = _enum(List=0, ParamOnUnset=1, Param=2, NoParam=3, Status=4)


def ircLower(string):
	return string.lower().replace("[", "{").replace("]", "}").replace("\\", "|")

class CaseInsensitiveDictionary(MutableMapping):
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
	return datetime.utcnow().replace(microsecond=0)

def timestamp(time):
	unixEpoch = datetime.utcfromtimestamp(0)
	return int((time - unixEpoch).total_seconds())


def durationToSeconds(durationStr):
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


ipv4MappedAddr = re.compile("::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
def unmapIPv4(ip):
	mapped = ipv4MappedAddr.match(ip)
	if mapped:
		return mapped.group(1)
	return ip


def unescapeEndpointDescription(desc):
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


def splitMessage(message, maxLength):
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
		elif " " in limitedMessage:
			pos = limitedMessage.rfind(" ")
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
	return format_chars.sub('', message)