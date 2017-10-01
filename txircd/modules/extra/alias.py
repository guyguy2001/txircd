from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from zope.interface import implementer
import re

validCommand = re.compile(r"^[A-Z]+$")

@implementer(IPlugin, IModuleData)
class CommandAlias(ModuleData):
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
				replaceCommand, replacementParams = replacement.split(" ", 1)
				if not validCommand.match(replaceCommand):
					raise ConfigValidationError("command_aliases", "replacement \"{}\" is not a valid command".format(replaceCommand))
				if replaceCommand in config["command_aliases"]: # Prevent infinite recursion by disallowing aliases of aliases
					raise ConfigValidationError("command_aliases", "replacement \"{}\" may not be used as a replacement because it is an alias".format(replaceCommand))
				escaped = False
				previousWasDollar = False
				for character in replacementParams:
					if previousWasDollar:
						if not character.isdigit():
							raise ConfigValidationError("command_aliases", "replacement \"{}\" doesn't correctly pass parameters; parameters must be passed using only numbers, e.g. $2 or $4-".format(replaceCommand))
						previousWasDollar = False
						continue
					if escaped:
						escaped = False
						continue
					if character == "$":
						previousWasDollar = True
					elif character == "\\":
						escaped = True
				if escaped:
					raise ConfigValidationError("command_aliases", "replacement \"{}\" escapes the end of the string".format(replaceCommand))
				if previousWasDollar:
					raise ConfigValidationError("command_aliases", "replacement \"{}\" terminates with an incomplete parameter replacement".format(replaceCommand))

@implementer(ICommand)
class UserAlias(Command):
	def __init__(self, replacement):
		self.replacement = replacement
	
	def parseParams(self, user, params, prefix, tags):
		return {
			"params": params,
			"prefix": prefix,
			"tags": tags
		}
	
	def execute(self, user, data):
		origParams = data["params"]
		command, replaceParams = self.replacement.split(" ", 1)
		assembledParams = []
		escaped = False
		readingVariable = False
		variableParameterData = []
		for paramChar in replaceParams:
			if escaped:
				assembledParams.append(paramChar)
				escaped = False
				continue
			if readingVariable:
				if paramChar.isdigit():
					variableParameterData.append(paramChar)
					continue
				startingParamNumber = int("".join(variableParameterData)) - 1
				variableParameterData = []
				readingVariable = False
				if paramChar == "-":
					assembledParams.append(" ".join(origParams[startingParamNumber:]))
					continue
				if startingParamNumber < len(origParams):
					assembledParams.append(origParams[startingParamNumber])
			if paramChar == "$":
				readingVariable = True
				continue
			if paramChar == "\\":
				escaped = True
				continue
			assembledParams.append(paramChar)
		if readingVariable:
			startingParamNumber = int("".join(variableParameterData)) - 1
			if startingParamNumber < len(origParams):
				assembledParams.append(origParams[startingParamNumber])
		
		paramsString = "".join(assembledParams)
		lastParam = None
		if " :" in paramsString:
			paramsString, lastParam = paramsString.split(" :", 1)
		params = paramsString.split(" ")
		if lastParam:
			params.append(lastParam)
		user.handleCommand(command, params, data["prefix"], data["tags"])
		return True

commandAlias = CommandAlias()