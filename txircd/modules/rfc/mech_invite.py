from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, IMode, ModuleData, Mode
from txircd.utils import ModeType, now
from zope.interface import implements

class Invite(ModuleData, Mode):
	implements(IPlugin, IModuleData, IMode)
	
	name = "Invite"
	core = True
	affectedActions = { "joinpermission": 10 }
	
	def channelModes(self):
		return [ ("i", ModeType.NoParam, self) ]
	
	def actions(self):
		return [ ("modeactioncheck-channel-i-joinpermission", 1, self.hasInviteMode),
				("join", 1, self.clearInvite),
				("commandpermission-INVITE", 1, self.checkInviteLevel) ]
	
	def userCommands(self):
		return [ ("INVITE", 1, UserInvite(self.ircd)) ]
	
	def serverCommands(self):
		return [ ("INVITE", 1, ServerInvite(self.ircd)) ]
	
	def hasInviteMode(self, channel, alsoChannel, user):
		if "i" in channel.modes:
			return True
		return None
	
	def clearInvite(self, channel, user):
		if "invites" not in user.cache:
			return
		if channel.name in user.cache["invites"]:
			del user.cache["invites"][channel.name]

	def checkInviteLevel(self, user, data):
		channel = data["channel"]
		if user not in channel.users:
			user.sendMessage(irc.ERR_NOTONCHANNEL, channel.name, "You're not on that channel")
			return False
		if not self.ircd.runActionUntilValue("checkchannellevel", "invite", channel, user):
			user.sendMessage(irc.ERR_CHANOPRIVSNEEDED, channel.name, "You don't have permission to invite users to {}".format(channel.name))
			return False
		return None
	
	def apply(self, actionName, channel, param, joiningChannel, user):
		if "invites" not in user.cache or channel.name not in user.cache["invites"]:
			user.sendMessage(irc.ERR_INVITEONLYCHAN, joiningChannel.name, "Cannot join channel (Invite only)")
			return False
		if user.cache["invites"][channel.name] < channel.existedSince:
			# The invite is older than the channel, so the channel was destroyed and recreated since the invite occurred
			del user.cache["invites"][channel.name]
			user.sendMessage(irc.ERR_INVITEONLYCHAN, joiningChannel.name, "Cannot join channel (Invite only)")
			return False
		return None


class UserInvite(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 2:
			user.sendSingleError("InviteCmd", irc.ERR_NEEDMOREPARAMS, "INVITE", "Not enough parameters")
			return None
		if params[0] not in self.ircd.userNicks:
			user.sendSingleError("InviteCmd", irc.ERR_NOSUCHNICK, params[0], "No such nick")
			return None
		if params[1] not in self.ircd.channels:
			user.sendSingleError("InviteCmd", irc.ERR_NOSUCHCHANNEL, params[1], "No such channel")
			return None
		return {
			"invitee": self.ircd.users[self.ircd.userNicks[params[0]]],
			"channel": self.ircd.channels[params[1]]
		}
	
	def affectedChannels(self, user, data):
		return [ data["channel"] ]
	
	def execute(self, user, data):
		targetUser = data["invitee"]
		channel = data["channel"]
		if targetUser in channel.users:
			user.sendMessage(irc.ERR_USERONCHANNEL, targetUser.nick, channel.name, "is already on channel")
			return True
		user.sendMessage(irc.RPL_INVITING, targetUser.nick, channel.name)
		if targetUser.uuid[:3] != self.ircd.serverID:
			self.ircd.servers[targetUser.uuid[:3]].sendMessage("INVITE", targetUser.uuid, channel.name, prefix=user.uuid)
			return True
		if "invites" not in targetUser.cache:
			targetUser.cache["invites"] = {}
		targetUser.cache["invites"][channel.name] = now()
		targetUser.sendMessage("INVITE", channel.name, sourceuser=user)
		self.ircd.runActionStandard("invite", user, targetUser, channel)
		return True


class ServerInvite(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, server, params, prefix, tags):
		if prefix not in self.ircd.users:
			return None
		if len(params) != 2:
			return None
		if params[1] not in self.ircd.channels:
			return None
		if params[0] not in self.ircd.users:
			return {} # If it's a local user who quit before we received the INVITE that was sent before the quit, that's fine
		return {
			"inviter": self.ircd.users[prefix],
			"invitee": self.ircd.users[params[0]],
			"channel": self.ircd.channels[params[1]]
		}
	
	def execute(self, server, data):
		if not data:
			return True
		user = data["inviter"]
		targetUser = data["invitee"]
		channel = data["channel"]
		if targetUser.uuid[:3] != self.ircd.serverID: # Needs more hops.
			self.ircd.servers[targetUser.uuid[:3]].sendMessage("INVITE", targetUser.uuid, channel.name, prefix=user.uuid)
			return True
		if "invites" not in targetUser.cache:
			targetUser.cache["invites"] = {}
		targetUser.cache["invites"][channel.name] = now()
		targetUser.sendMessage("INVITE", channel.name, sourceuser=user)
		self.ircd.runActionStandard("invite", user, targetUser, channel)
		return True

inviteMechanism = Invite()