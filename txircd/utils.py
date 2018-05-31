from collections import MutableMapping
from datetime import datetime
from enum import IntEnum
from typing import List
import re

validNick = re.compile(r"^[a-zA-Z\-\[\]\\`^{}_|][a-zA-Z0-9\-\[\]\\`^{}_|]*$")
def isValidNick(nick: str) -> bool:
	"""
	Determines whether the provided nickname is in a valid format.
	"""
	return validNick.match(nick)

def isValidIdent(ident: str) -> bool:
	"""
	Determines whether the provided ident is in a valid format.
	"""
	for character in ident:
		if not character.isalnum() and character not in "-.[\]^_`{|}":
			return False
	return True

validHost = re.compile(r"^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*$")
def isValidHost(host: str) -> bool:
	"""
	Determines whether the provided hostname is in a valid format.
	"""
	return validHost.match(host)

def isValidChannelName(channelName: str) -> bool:
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
def isValidMetadataKey(key: str) -> bool:
	"""
	Determines whether the given metadata key is in a valid format.
	"""
	return validMetadataKey.match(key)


def lenBytes(string: str) -> int:
	return len(string.encode("utf-8"))


class ModeType(IntEnum):
	List = 0
	ParamOnUnset = 1
	Param = 2
	NoParam = 3
	Status = 4


def ircLower(string: str) -> str:
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


def now() -> datetime:
	"""
	Returns a datetime object representing now.
	"""
	return datetime.utcnow()

def timestamp(time: datetime) -> float:
	"""
	Converts a datetime object to a Unix timestamp.
	"""
	unixEpoch = datetime.utcfromtimestamp(0)
	return (time - unixEpoch).total_seconds()

def timestampStringFromTime(time: datetime) -> str:
	"""
	Converts a datetime object to the string representation of its Unix timestamp.
	"""
	return timestampStringFromTimestamp(timestamp(time))

def timestampStringFromTimeSeconds(time: datetime) -> str:
	"""
	Converts a datetime object to the string representation of its Unix timestamp,
	truncated to whole seconds.
	"""
	return timestampStringFromTimestampSeconds(timestamp(time))

def timestampStringFromTimestamp(timestamp: float) -> str:
	"""
	Converts a Unix timestamp to its string representation.
	"""
	return format(timestamp, ".6f").rstrip("0").rstrip(".")

def timestampStringFromTimestampSeconds(timestamp: float) -> str:
	"""
	Converts a Unix timestamp to its string representation, truncated to whole seconds.
	"""
	return str(int(timestamp))

def isoTime(time: datetime) -> str:
	"""
	Converts a datetime object to an ISO-format date.
	"""
	if time.microsecond == 0:
		time = time.replace(microsecond=1) # Force milliseconds to appear
	return "{}Z".format(time.isoformat()[:-3])


def durationToSeconds(durationStr: str) -> int:
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


def unescapeEndpointDescription(desc: str) -> str:
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
				char = next(desc)
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


def trimStringToByteLength(strToTrim: str, byteLen: int) -> str:
	"""
	Trims a string to a given maximum number of bytes.
	The resulting string may encode to fewer than the given number
	of bytes, but it won't be longer.
	"""
	trimmedStr = strToTrim[:byteLen]
	while lenBytes(trimmedStr) > byteLen:
		trimmedStr = trimmedStr[:-1] # Keep trimming the string until it fits in the byte limit
	return trimmedStr


def splitMessage(message: str, maxLength: int, splitOnCharacter: str = " ") -> List[str]:
	"""
	Split a string into a series of strings each with maximum byte length
	maxLength and returns them in a list.
	"""
	msgList = []
	while message:
		limitedMessage = trimStringToByteLength(message, maxLength)
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
def stripFormatting(message: str) -> str:
	"""
	Removes IRC formatting from the provided message.
	"""
	return format_chars.sub('', message)