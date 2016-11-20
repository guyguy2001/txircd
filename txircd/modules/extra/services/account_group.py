from twisted.plugin import IPlugin
from twisted.web.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

class AccountGroup(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountGroup"
	
	def userCommands(self):
		return [ ("ACCOUNTGROUP", 1, CommandGroup(self.ircd)),
			("ACCOUNTUNGROUP", 1, CommandUngroup(self.ircd)) ]

class CommandGroup(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		return {}
	
	def execute(self, user, data):
		if not user.metadataKeyExists("account"):
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "GROUP", "NOTLOGIN")
			user.sendMessage("NOTICE", "You're not logged in.")
			return True
		resultValue = self.ircd.runActionUntilValue("accountaddnick", user.metadataValue("account"), user.nick)
		if not resultValue:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "GROUP", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if resultValue[0]:
			user.sendMessage("NOTICE", "{} was successfully linked to your account.".format(user.nick))
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "GROUP", resultValue[1])
		user.sendMessage("NOTICE", "Couldn't group nick: {}".format(resultValue[2]))
		return True

class CommandUngroup(Command):
	implements(ICommand)
	
	def __init__(self, ircd):
		self.ircd = ircd
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			user.sendSingleError("UngroupParams", irc.ERR_NEEDMOREPARAMS, "UNGROUP", "Not enough parameters")
			return None
		return {
			"removenick": params[0]
		}
	
	def execute(self, user, data):
		if not user.metadataKeyExists("account"):
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "GROUP", "NOTLOGIN")
			user.sendMessage("NOTICE", "You're not logged in.")
			return True
		removeNick = data["removenick"]
		resultValue = self.ircd.runActionUntilValue("accountremovenick", user.metadataValue("account"), removeNick)
		if not resultValue:
			user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "GROUP", "NOACCOUNT")
			user.sendMessage("NOTICE", "This server doesn't have accounts set up.")
			return True
		if resultValue[0]:
			user.sendMessage("NOTICE", "{} was successfully removed from your account.".format(removeNick))
			return True
		user.sendMessage(irc.ERR_SERVICES, "ACCOUNT", "GROUP", resultValue[1])
		user.sendMessage("NOTICE", "Couldn't ungroup nick: {}".format(resultValue[2]))
		return True

groupCommand = AccountGroup()