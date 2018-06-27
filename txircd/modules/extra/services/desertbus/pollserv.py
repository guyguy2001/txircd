from twisted.internet import reactor
from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import durationToSeconds, now, timestampStringFromTime
from zope.interface import implementer
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from weakref import WeakKeyDictionary

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

@implementer(IPlugin, IModuleData)
class PollService(ModuleData):
	name = "PollService"
	
	question = ""
	answers = []
	startTime = None
	endTime = None
	pollTimer = None
	serverResults = WeakKeyDictionary()
	collectingResults = False
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("statsruntype-poll", 10, self.statsPollAnswers),
			("burst", 5, self.burst),
			("commandpermission-POLLQUESTION", 10, self.checkPollQuestionAdmin),
			("commandpermission-POLLADDANSWER", 10, self.checkPollAddAnswerAdmin),
			("commandpermission-POLLREMOVEANSWER", 10, self.checkPollRemoveAnswerAdmin),
			("commandpermission-POLLSTART", 10, self.checkPollStartAdmin),
			("commandpermission-POLLCANCEL", 10, self.checkPollCancelAdmin),
			("commandpermission-POLLEND", 10, self.checkPollEndAdmin) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("POLLQUESTION", 1, PollQuestionCmd(self)),
			("POLLADDANSWER", 1, PollAddAnswerCmd(self)),
			("POLLREMOVEANSWER", 1, PollRemoveAnswerCmd(self)),
			("POLLSTART", 1, StartPollCmd(self)),
			("VOTE", 1, VoteCmd(self)),
			("CURRENTPOLL", 1, CurrentPollCmd(self)),
			("POLLCANCEL", 1, CancelPollCmd(self)),
			("POLLEND", 1, EndPollCmd(self)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("POLLSTART", 1, ServerStartPollCmd(self)),
			("POLLCANCEL", 1, ServerPollCancelCmd(self)),
			("POLLEND", 1, ServerPollEndCmd(self)),
			("VOTEDATA", 1, ServerVoteDataCmd(self)) ]
	
	def unload(self) -> None:
		self.removeAllVotes()
		if self.pollRunning():
			self.pollTimer.cancel()
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "poll_announce_bot" in config:
			if not isinstance(config["poll_announce_bot"], str):
				raise ConfigValidationError("poll_announce_bot", "must be a string")
		else:
			config["poll_announce_bot"] = ""
		if "poll_announce_channels" in config:
			if not isinstance(config["poll_announce_channels"], list):
				raise ConfigValidationError("poll_announce_channels", "must be a list of channel names")
			for channelName in config["poll_announce_channels"]:
				if not isinstance(channelName, str):
					raise ConfigValidationError("poll_annnounce_channels", "must be a list of channel names")
		else:
			config["poll_announce_channels"] = []
	
	def statsPollAnswers(self) -> Dict[str, str]:
		info = {}
		for index, answer in enumerate(self.answers):
			info[str(index + 1)] = answer
		return info
	
	def burst(self, server: "IRCServer") -> None:
		if self.pollRunning():
			answerTags = {}
			for index, answer in self.answers:
				answerTags["answer{}".format(index)] = answer
			secondsRemaining = (self.endTime - now()).seconds
			server.sendMessage("POLLSTART", self.startTime, secondsRemaining, self.question, prefix=self.ircd.serverID, tags=answerTags)
	
	def checkPollAdmin(self, user: "IRCUser", operPermission: str) -> Optional[bool]:
		if not self.ircd.runActionUntilValue("userhasoperpermission", user, operPermission, users=[user]):
			user.sendMessage(irc.ERR_NOPRIVILEGES, "Permission denied - You do not have the correct operator privileges")
			return False
		return None
	
	def checkPollQuestionAdmin(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		return self.checkPollAdmin(user, "command-pollquestion")
	
	def checkPollAddAnswerAdmin(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		return self.checkPollAdmin(user, "command-polladdanswer")
	
	def checkPollRemoveAnswerAdmin(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		return self.checkPollAdmin(user, "command-pollremoveanswer")
	
	def checkPollStartAdmin(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		return self.checkPollAdmin(user, "command-pollstart")
	
	def checkPollCancelAdmin(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		return self.checkPollAdmin(user, "command-pollcancel")
	
	def checkPollEndAdmin(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		return self.checkPollAdmin(user, "command-pollend")
	
	def getBotAnnounceUser(self) -> Optional["IRCUser"]:
		botNick = self.ircd.config["poll_announce_bot"]
		if not botNick:
			return None
		if botNick not in self.ircd.userNicks:
			return None
		return self.ircd.userNicks[botNick]
	
	def sendMessageFromBot(self, toUser: "IRCUser", command: str, *args: str, **kw: Dict[str, Any]) -> None:
		responseBot = self.getBotAnnounceUser()
		if not responseBot:
			toUser.sendMessage(command, *args, **kw)
			return
		kw["prefix"] = responseBot.hostmask()
		toUser.sendMessage(command, *args, **kw)
	
	def sendBatchedErrorFromBot(self, toUser: "IRCUser", batchName: str, command: str, *args: str, **kw: Dict[str, Any]) -> None:
		responseBot = self.getBotAnnounceUser()
		if not responseBot:
			toUser.sendBatchedError(batchName, command, *args, **kw)
			return
		kw["prefix"] = responseBot.hostmask()
		toUser.sendBatchedError(batchName, command, *args, **kw)
	
	def sendAnnouncement(self, messageToAnnounce: str) -> None:
		botUser = self.getBotAnnounceUser()
		msgPrefix = self.ircd.name
		if botUser:
			msgPrefix = botUser.hostmask()
		for channelName in self.ircd.config["poll_announce_channels"]:
			if channelName in self.ircd.channels:
				self.ircd.channels[channelName].sendUserMessage("PRIVMSG", messageToAnnounce, prefix=msgPrefix)
	
	def setQuestion(self, question: str) -> None:
		self.question = question
		self.answers = []
	
	def clearQuestion(self) -> None:
		self.setQuestion("")
	
	def startPoll(self, seconds: int, startTime: "datetime" = None, byUser: "IRCUser" = None, fromServer: "IRCServer" = None) -> bool:
		if self.pollRunning():
			return False
		if not self.question:
			return False
		if not self.answers:
			return False
		if seconds < 1:
			return False
		answerTags = {}
		for index, answer in self.answers:
			answerTags["answer{}".format(index)] = answer
		self.removeAllVotes()
		pollTime = now()
		self.ircd.broadcastToServers(fromServer, "POLLSTART", pollTime, seconds, self.question, prefix=self.ircd.serverID if byUser is None else byUser.uuid, tags=answerTags)
		self.pollTimer = reactor.callLater(seconds, self.endQuestion)
		self.startTime = now() if startTime is None else startTime
		self.endTime = self.startTime + timedelta(seconds=seconds)
		self.announcePoll(byUser)
		return True
	
	def startPollFromRemote(self, question: str, answers: List[str], seconds: int, questionTime: "datetime", byUser: "IRCUser", fromServer: "IRCServer") -> bool:
		if self.pollRunning():
			if questionTime > self.startTime:
				return False
			if questionTime == self.startTime:
				self.cancelQuestion(fromServer)
				return True
		elif self.pollActive():
			return False # Don't interrupt result collection with a new question
		self.question = question
		self.answers = answers
		self.startPoll(seconds, questionTime, byUser, fromServer)
		return True
	
	def endQuestion(self, byUser: "IRCUser" = None, fromServer: "IRCServer" = None) -> None:
		message = "\x0312\x02Poll ended!\x02\x03"
		if byUser is not None:
			message = "{} (Ended by {})".format(message, byUser.nick)
			messagePrefix = byUser.uuid
		else:
			messagePrefix = self.ircd.serverID
		self.sendAnnouncement(message)
		self.collectingResults = True
		self.startTime = None
		self.endTime = None
		if self.pollTimer.active():
			self.pollTimer.cancel()
		self.pollTimer = None
		self.broadcastToServers(fromServer, "POLLEND", prefix=messagePrefix)
	
	def cancelQuestion(self, fromServer: "IRCServer" = None) -> bool:
		if not self.pollRunning():
			return False
		self.pollTimer.cancel()
		self.pollTimer = None
		self.question = ""
		self.answers = []
		self.removeAllVotes()
		self.ircd.broadcastToServers(fromServer, "POLLCANCEL", timestampStringFromTime(self.startTime), prefix=self.ircd.serverID)
		return False
	
	def pollActive(self) -> bool:
		if self.pollRunning():
			return True
		if self.collectingResults:
			return True
		return False
	
	def pollRunning(self) -> bool:
		return self.pollTimer and self.pollTimer.active()
	
	def getServerResults(self) -> List[int]:
		results = []
		for _ in self.answers:
			results.append(0)
		for user in self.ircd.users.values():
			if "poll-answer" in user.cache:
				results[user.cache["poll-answer"]] += 1
		return results
	
	def removeAllVotes(self) -> None:
		for user in self.ircd.users.itervalues():
			if "poll-answer" in user.cache:
				del user.cache["poll-answer"]
	
	def announcePoll(self, byUser: "IRCUser" = None) -> None:
		self.sendAnnouncement("\x0312\x02New poll!\x02 \x0303{}".format(self.question))
		for index, answer in enumerate(self.answers):
			self.sendAnnouncement("\x0304{}: \x02{}".format(index + 1, answer))
		self.sendAnnouncement("\x0312Vote using \x02/vote \x1fnumber\x1f\x02 (using the number of each answer)")
	
	def checkServerResults(self) -> bool:
		for server in self.ircd.servers.values():
			if server not in self.serverResults:
				return False
		return True
	
	def announceResults(self) -> None:
		results = self.getServerResults()
		for serverResults in self.serverResults.values():
			for index, answerCount in enumerate(serverResults):
				results[index] += answerCount
		self.sendAnnouncement("\x0304\x02Poll results:")
		for index, answerCount in enumerate(results):
			self.sendAnnouncement("\x0304{} votes: {}".format(answerCount, self.answers[index]))

@implementer(ICommand)
class PollQuestionCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			user.sendSingleError("PollQuestionParams", irc.ERR_NEEDMOREPARAMS, "POLLQUESTION", "Not enough parameters")
			return None
		return {
			"question": " ".join(params)
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if self.module.pollActive():
			user.sendMessage(irc.ERR_SERVICES, "POLL", "RUNNING", "A poll is already running.")
			self.module.sendMessageFromBot(user, "NOTICE", "A poll is already running.")
			return True
		self.module.setQuestion(data["question"])
		self.module.sendMessageFromBot(user, "NOTICE", "Question \"{}\" added.")
		return True

@implementer(ICommand)
class PollAddAnswerCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("PollAnswerParams", irc.ERR_NEEDMOREPARAMS, "POLLANSWER", "Not enough parameters")
			return None
		return {
			"answer": " ".join(params[1:])
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if self.module.pollActive():
			user.sendMessage(irc.ERR_SERVICES, "POLL", "RUNNING", "A poll is currently running.")
			self.module.sendMessageFromBot(user, "NOTICE", "A poll is currently running.")
			return True
		self.module.answers.append(data["answer"])
		self.module.sendMessageFromBot(user, "NOTICE", "Answer \"{}\" added.".format(data["answer"]))
		return True

@implementer(ICommand)
class PollRemoveAnswerCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params:
			user.sendSingleError("PollRemoveAnswerParams", irc.ERR_NEEDMOREPARAMS, "POLLREMOVEANSWER", "Not enough parameters")
			return None
		answerToDelete = 0
		try:
			answerToDelete = int(params[0])
		except ValueError:
			pass # Let this get caught by the if condition below
		if answerToDelete < 1 or answerToDelete > len(self.module.answers):
			user.startErrorBatch("PollRemoveAnswerChoice")
			user.sendBatchedError("PollRemoveAnswerChoice", irc.ERR_SERVICES, "POLL", "INVALIDCHOICE", "A poll answer number must be chosen.")
			self.module.sendBatchedErrorFromBot(user, "PollRemoveAnswerChoice", "NOTICE", "A poll answer number must be chosen.")
			return None
		return {
			"answerindex": answerToDelete - 1
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if self.module.pollActive():
			user.sendMessage(irc.ERR_SERVICES, "POLL", "RUNNING", "A poll is currently running.")
			self.module.sendMessageFromBot(user, "NOTICE", "A poll is currently running.")
			return True
		answerIndex = data["answerindex"]
		answerText = self.module.answers[answerIndex]
		del self.module.answers[answerIndex]
		self.module.sendMessageFromBot(user, "NOTICE", "Answer \"{}\" removed.".format(answerText))
		return True

@implementer(ICommand)
class StartPollCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			user.sendSingleError("StartPollParams", irc.ERR_NEEDMOREPARAMS, "POLLSTART", "Not enough parameters")
			return None
		return {
			"duration": durationToSeconds(params[0])
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		durationSeconds = data["duration"]
		if durationSeconds < 1:
			user.sendMessage(irc.ERR_SERVICES, "POLL", "BADTIME", "Choose a time in the future for the poll to end.")
			self.module.sendMessageFromBot(user, "NOTICE", "Choose a time in the future for the poll to end.")
			return True
		if self.module.pollActive():
			user.sendMessage(irc.ERR_SERVICES, "POLL", "RUNNING", "A poll is currently running.")
			self.module.sendMessageFromBot(user, "NOTICE", "A poll is currently running.")
			return True
		if self.module.question == "" or not self.module.answers:
			user.sendMessage(irc.ERR_SERVICES, "POLL", "NOQUESTION", "No question is set.")
			self.module.sendMessageFromBot(user, "NOTICE", "No question is set.")
			return True
		if not self.module.answers:
			user.sendMessage(irc.ERR_SERVICES, "POLL", "NOANSWERS", "No answers were entered.")
			self.module.sendMessageFromBot(user, "NOTICE", "No answers were entered.")
			return True
		self.module.startPoll(durationSeconds)
		self.module.sendMessageFromBot(user, "NOTICE", "Started the poll!")
		return True

@implementer(ICommand)
class VoteCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			user.sendSingleError("VoteParams", irc.ERR_NEEDMOREPARAMS, "VOTE", "Not enough parameters")
			return None
		voteNum = None
		try:
			voteNum = int(params[0])
		except ValueError:
			user.startErrorBatch("VoteChoice")
			user.sendBatchedError("VoteChoice", irc.ERR_SERVICES, "POLL", "BADANSWER", "Your selection must be a number to select.")
			self.module.sendBatchedErrorFromBot(user, "VoteChoice", "NOTICE", "Your selection must be a number to select.")
			return None
		return {
			"answer": voteNum
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if not self.module.pollRunning():
			user.sendMessage(irc.ERR_SERVICES, "POLL", "NOTRUNNING", "The poll is not currently running.")
			self.module.sendMessageFromBot(user, "NOTICE", "The poll is not currently running.")
			return True
		voteNum = data["answer"] - 1
		if voteNum < 0 or voteNum >= len(self.module.answers):
			user.sendMessage(irc.ERR_SERVICES, "POLL", "BADCHOICE", "That's not the ID of an answer to the poll.")
			self.module.sendMessageFromBot(user, "NOTICE", "That's not the ID of an answer to the poll.")
			return True
		hasOldAnswer = ("poll-answer" in user.cache)
		user.cache["poll-answer"] = voteNum
		answerName = self.module.answers[voteNum]
		if hasOldAnswer:
			self.module.sendMessageFromBot(user, "NOTICE", "You changed your vote to \"{}\".".format(answerName))
		else:
			self.module.sendMessageFromBot(user, "NOTICE", "You voted for \"{}\".".format(answerName))
		return True

@implementer(ICommand)
class CurrentPollCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if not self.module.pollRunning():
			self.module.sendMessageFromBot(user, "NOTICE", "No poll is currently running.")
			return True
		self.module.sendMessageFromBot(user, "NOTICE", "Question: {}".format(self.module.question))
		for answerIndex, answer in enumerate(self.module.answers):
			self.module.sendMessageFromBot(user, "NOTICE", "{}. {}".format(answerIndex + 1, answer))
		return True

@implementer(ICommand)
class CancelPollCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if not self.module.pollRunning():
			self.module.sendMessageFromBot(user, "NOTICE", "No poll is currently running.")
			return True
		if self.module.cancelQuestion():
			self.module.sendMessageFromBot(user, "NOTICE", "Poll canceled.")
		else:
			self.module.sendMessageFromBot(user, "NOTICE", "Failed to cancel poll.")
		return True

@implementer(ICommand)
class EndPollCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		self.module.endQuestion()
		self.module.sendMessageFromBot(user, "NOTICE", "Poll ended.")
		return True

@implementer(ICommand)
class ServerStartPollCmd(Command): # self.ircd.broadcastToServers("POLLSTART", pollTime, seconds, self.question, prefix=self.ircd.serverID if byUser is None else byUser.uuid, tags=answerTags)
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 3:
			return None
		pollTimestamp = None
		try:
			pollTimestamp = int(params[0])
		except ValueError:
			return None
		pollTime = None
		try:
			pollTime = datetime.utcfromtimestamp(pollTimestamp)
		except (OSError, OverflowError, ValueError):
			return None
		seconds = None
		try:
			seconds = int(params[1])
		except ValueError:
			return None
		question = params[2]
		answers = []
		answerIndex = 0
		while True:
			answerKey = "answer{}".format(answerIndex)
			if answerKey not in tags:
				break
			answers.append(tags[answerKey])
			answerIndex += 1
		if not answers:
			return None
		data = {
			"time": pollTime,
			"seconds": seconds,
			"question": question,
			"answers": answers
		}
		if prefix in self.ircd.users:
			data["user"] = self.ircd.users[prefix]
		return data
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.startPollFromRemote(data["question"], data["answers"], data["seconds"], data["time"], data["user"] if "user" in data else None, server)
		return True

@implementer(ICommand)
class ServerPollCancelCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 1:
			return None
		pollTimestamp = None
		try:
			pollTimestamp = int(params[0])
		except ValueError:
			return None
		pollTime = None
		try:
			pollTime = datetime.utcfromtimestamp(pollTimestamp)
		except (OSError, OverflowError, ValueError):
			return None
		return {
			"time": pollTime
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if data["time"] == self.module.startTime:
			self.module.cancelQuestion(server)
		return True

@implementer(ICommand)
class ServerPollEndCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if prefix in self.ircd.users:
			return {
				"user": self.ircd.users[prefix]
			}
		return {}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.endQuestion(data["user"] if "user" in data else None, server)
		voteResults = self.module.getServerResults()
		voteDataTags = {}
		for index, voteCount in enumerate(voteResults):
			voteDataTags["answer{}".format(index)] = str(voteCount)
		self.ircd.broadcastToServers(None, "VOTEDATA", prefix=self.ircd.serverID, tags=voteDataTags)
		return True

@implementer(ICommand)
class ServerVoteDataCmd(Command):
	def __init__(self, module: PollService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		voteCounts = []
		while True:
			answerTag = "answer{}".format(len(voteCounts))
			if answerTag not in tags:
				break
			try:
				voteCounts.append(int(tags[answerTag]))
			except ValueError:
				return None
		if prefix not in self.ircd.servers:
			return None
		return {
			"from": self.ircd.servers[prefix],
			"votes": voteCounts,
			"tags": tags
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.serverResults[data["from"]] = data["votes"]
		if self.module.checkServerResults():
			self.module.announceResults()
			self.module.serverResults.clear()
			self.module.clearQuestion()
			self.module.collectingResults = False
		self.ircd.broadcastToServers(server, "VOTEDATA", prefix=data["from"].serverID, tags=data["tags"])
		return True

pollServ = PollService()