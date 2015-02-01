from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements

class UserCommand(Command, ModuleData):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "UserCommand"
	core = True
	forRegistered = False
	
	def userCommands(self):
		return [ ("USER", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		if len(params) < 4:
			user.sendSingleError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", "Not enough parameters")
			return None
		if not params[3]: # Make sure the gecos isn't an empty string
			user.sendSingleError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", "Not enough parameters")
			return None
		params[0] = params[0][:12] # Trim down to 12 characters to guarantee it won't be rejected by the user class for being too long
		for char in params[0]: # Validate the ident
			if not char.isalnum() and char not in "-.[\]^_`{|}":
				user.sendSingleError("UserCmd", irc.ERR_NEEDMOREPARAMS, "USER", "Your username is not valid") # The RFC is dumb.
				return None
		return {
			"ident": params[0],
			"gecos": params[3]
		}
	
	def execute(self, user, data):
		user.changeIdent(data["ident"])
		user.changeGecos(data["gecos"])
		user.register("USER")
		return True

cmd_user = UserCommand()