from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implements
import re

validCommand = re.compile(r"^[A-Z]+$")

class CommandAlias(ModuleData):
	implements(IPlugin, IModuleData)

	name = "CommandAlias"

	def userCommands(self):
		commands = []
		for command, replacement in self.ircd.config.get("command_aliases", {}).iteritems():
			commands.append((command, 1, UserAlias(replacement)))
		return commands

	def verifyConfig(self, config):
		if "command_aliases" in config:
			if not isinstance(config["command_aliases"], dict):
				raise ConfigValidationError("command_aliases", "value must be a dictionary")
			for command, replacement in config["command_aliases"].iteritems():
				if not isinstance(command, basestring) or not validCommand.match(command):
					raise ConfigValidationError("command_aliases", "alias \"{}\" is not a valid command".format(command))
				if not isinstance(replacement, basestring):
					raise ConfigValidationError("command_aliases", "replacement \"{}\" must be a string".format(replacement))
				if any(replacementPart.startswith(":") for replacementPart in replacementParts) and "%p" in replacement:
					raise ConfigValidationError("command_aliases", "replacement \"{}\" cannot have a final parameter in conjunction with %p".format(replacement))
				replaceCommand = replacement.split(' ', 1)[0]
				if not validCommand.match(replaceCommand):
					raise ConfigValidationError("command_aliases", "replacement \"{}\" is not a valid command".format(replaceCommand))
				if replaceCommand in config["command_aliases"]: # Prevent infinite recursion by disallowing aliases of aliases
					raise ConfigValidationError("command_aliases", "replacement \"{}\" may not be used as a replacement because it is an alias".format(replaceCommand))

class UserAlias(Command):
	implements(ICommand)

	def __init__(self, replacement):
		self.replacement = replacement

	def parseParams(self, user, params, prefix, tags):
		return {
			"params": params,
			"prefix": prefix,
			"tags": tags
		}

	def execute(self, user, data):
		if " :" in self.replacement:
			params, lastParam = self.replacement.split(" :", 1)
		else:
			params = self.replacement
			lastParam = None
		replacementParts = [x if x != "%p" else " ".join(data["params"]) for x in params.split(" ")]
		if lastParam:
			replacementParts.append(lastParam)
		user.handleCommand(replacementParts[0], replacementParts[1:], data["prefix"], data["tags"])
		return True

commandAlias = CommandAlias()
