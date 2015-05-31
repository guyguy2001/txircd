from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IMode, IModuleData, Mode, ModuleData
from txircd.utils import ModeType, now, timestamp
from zope.interface import implements
from weakref import WeakKeyDictionary

irc.ERR_CANNOTKNOCK  = "480"
irc.RPL_KNOCK = "710"
irc.RPL_KNOCKDLVR = "711"
irc.ERR_TOOMANYKNOCK = "712"
irc.ERR_CHANOPEN = "713"
irc.ERR_KNOCKONCHAN = "714"

class Knock(ModuleData):
	implements(IPlugin, IModuleData)

	name = "Knock"

	def actions(self):
		return [ ("modeactioncheck-channel-K-commandpermission-KNOCK", 10, self.channelHasMode),
				("invite", 1, self.clearKnocksOnInvite) ]

	def userCommands(self):
		return [ ("KNOCK", 1, KnockCommand(self.ircd)) ]

	def channelModes(self):
		return [ ("K", ModeType.NoParam, NoKnockMode()) ]

	def verifyConfig(self, config):
		if "knock_delay" in config and (not isinstance(config["knock_delay"], int) or config["knock_delay"] < 0):
			raise ConfigValidationError("knock_delay", "invalid number")

	def channelHasMode(self, channel, user, data):
		if "K" in channel.modes:
			return ""
		return None

	def clearKnocksOnInvite(self, user, targetUser, channel):
		if "knocks" in targetUser.cache and channel in targetUser.cache["knocks"]:
			del targetUser.cache["knocks"][channel]

class KnockCommand(Command):
	implements(ICommand)

	def __init__(self, ircd):
		self.ircd = ircd

	def parseParams(self, user, params, prefix, tags):
		self.expireKnocks(user)
		if not params:
			user.sendSingleError("KnockParams", irc.ERR_NEEDMOREPARAMS, "KNOCK", "Not enough paramters")
			return None
		if params[0] not in self.ircd.channels:
			user.sendSingleError("KnockParams", irc.ERR_NOSUCHCHANNEL, params[0], "No such channel")
			return None
		channel = self.ircd.channels[params[0]]
		if user in channel.users:
			user.sendSingleError("KnockParams", irc.ERR_KNOCKONCHAN, params[0], "Can't KNOCK on {}, you are already on that channel".format(params[0]))
			return None
		if "i" not in channel.modes:
			user.sendSingleError("KnockParams", irc.ERR_CHANOPEN, params[0], "Can't KNOCK on {}, channel is open".format(params[0]))
			return None
		if "knocks" in user.cache and channel in user.cache["knocks"]:
			user.sendSingleError("KnockParams", irc.ERR_TOOMANYKNOCK, params[0], "Can't KNOCK on {}, (only one KNOCK per {} seconds allowed)".format(params[0], self.ircd.config.get("knock_delay", 300)))
			return None
		return {
			"channel": channel,
			"reason": " ".join(params[1:]) if len(params) > 1 else "has asked for an invite"
		}

	def execute(self, user, data):
		channel = data["channel"]
		if "knocks" not in user.cache:
			user.cache["knocks"] = WeakKeyDictionary()
		user.cache["knocks"][channel] = timestamp(now())
		reason = data["reason"]
		for targetUser in channel.users:
			if self.ircd.runActionUntilValue("checkchannellevel", "invite", channel, user):
				targetUser.sendMessage(irc.RPL_KNOCK, channel.name, user.nick, reason)
		user.sendMessage(irc.RPL_KNOCKDLVR, channel.name, "Your KNOCK has been delivered")
		return True

	def affectedChannels(self, user, data):
		return [data["channel"]]

	def expireKnocks(self, user):
		if "knocks" not in user.cache:
			return
		expiredKnocks = []
		nowTS = timestamp(now())
		for channel, knockTime in user.cache["knocks"].iteritems():
			if knockTime + self.ircd.config.get("knock_delay", 300) <= nowTS:
				expiredKnocks.append(channel)
		for channel in expiredKnocks:
			del user.cache["knocks"][channel]

class NoKnockMode(Mode):
	implements(IMode)

	affectedActions = { "commandpermission-KNOCK": 10 }

	def apply(self, actionName, channel, param, user, data):
		user.sendMessage(irc.ERR_CANNOTKNOCK, channel.name, "Can't KNOCK on {}, +K is set".format(channel.name))
		return False

knock = Knock()