from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from txircd.user import LocalUser
from txircd.utils import isValidIdent, isValidHost, isValidNick, lenBytes, splitMessage
from zope.interface import implementer
from typing import Any, Dict

@implementer(IPlugin, IModuleData)
class ServerBots(ModuleData):
	name = "ServerBots"
	
	def load(self) -> None:
		self.botList = []
		for botNick, botData in self.ircd.config["server_bots"].items():
			botIdent = botData["ident"]
			botHost = botData["host"]
			botGecos = botData["gecos"]
			if botNick in self.ircd.userNicks:
				nickUser = self.ircd.userNicks[botNick]
				nickUser.changeNick(nickUser.uuid)
			botUser = LocalUser(self.ircd, botNick, botIdent, botHost, "127.0.0.1", botGecos)
			botUser.setSendMsgFunc(self.receiveBotMessageProcessor(botData))
			self.botList.append(botUser)
	
	def unload(self) -> None:
		for bot in self.botList:
			bot.disconnect("Unloading")
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "server_bots" not in config:
			config["server_bots"] = {}
			return
		if not isinstance(config["server_bots"], dict):
			raise ConfigValidationError("server_bots", "value must be a dictionary")
		for botName, botData in config["server_bots"].items():
			if not isinstance(botName, str):
				raise ConfigValidationError("server_bots", "keys must be strings")
			if lenBytes(botName) > self.ircd.config.get("nick_length", 32) or not isValidNick(botName):
				raise ConfigValidationError("server_bots", "key \"{}\" is not a valid nickname".format(botName))
			if not isinstance(botData, dict):
				raise ConfigValidationError("server_bots", "values must be dicts")
			for requiredDataKey in ("ident", "host", "gecos", "help_intro", "commands"):
				if requiredDataKey not in botData:
					raise ConfigValidationError("server_bots", "key \"{}\" not found in the bot {}'s data".format(requiredDataKey, botName))
			botIdent = botData["ident"]
			if lenBytes(botIdent) > self.ircd.config.get("ident_length", 12):
				raise ConfigValidationError("server_bots", "the ident for {} is not a valid ident".format(botName))
			if not isValidIdent(botIdent):
				raise ConfigValidationError("server_bots", "the ident for {} is not a vlaid ident".format(botName))
			botHost = botData["host"]
			if lenBytes(botHost) > self.ircd.config.get("host_length", 64) or not isValidHost(botHost):
				raise ConfigValidationError("server_bots", "the host for {} is not a valid host".format(botHost))
			botGecos = botData["gecos"]
			if lenBytes(botGecos) > self.ircd.config.get("gecos_length", 128):
				raise ConfigValidationError("server_bots", "the gecos for {} is not a valid gecos".format(botGecos))
			botHelpIntro = botData["help_intro"]
			if not isinstance(botHelpIntro, list):
				raise ConfigValidationError("server_bots", "help intro text must be a list of strings")
			for helpIntroLine in botHelpIntro:
				if not isinstance(helpIntroLine, str):
					raise ConfigValidationError("server_bots", "help intro text must be a list of strings")
			for command, commandData in botData["commands"].items():
				if not isinstance(command, str):
					raise ConfigValidationError("server_bots", "commands must be strings")
				if not command.isalpha() or not command.isupper() or lenBytes(command) > 50:
					raise ConfigValidationError("server_bots", "command \"{}\" is not a valid command (single word, all captial letters, of less than or equal to 50 characters")
				if "help" not in commandData:
					raise ConfigValidationError("server_bots", "help text not specified for command {}".format(command))
				helpText = commandData["help"]
				if not isinstance(helpText, str):
					raise ConfigValidationError("server_bots", "help text for command {} is not a string".foramt(command))
				if lenBytes(helpText) > 80:
					raise ConfigValidationError("server_bots", "help text for command {} is too long (more than 80 characters".format(helpText))
				if "detailed_help" not in commandData:
					raise ConfigValidationError("server_bots", "detailed help not specified for command {}".format(command))
				detailedHelp = commandData["detailed_help"]
				if not isinstance(detailedHelp, list):
					raise ConfigValidationError("server_bots", "detailed help for command {} must be a list of strings".format(command))
				for helpLine in detailedHelp:
					if not isinstance(helpLine, str):
						raise ConfigValidationError("server_bots", "detailed help for command {} must be a list of strings".format(command))
				if "execute" in commandData:
					executeLine = commandData["execute"]
					escaped = False
					previousWasDollar = False
					for character in executeLine:
						if previousWasDollar:
							if not character.isdigit():
								raise ConfigValidationError("server_bots", "execute line for command {} doesn't correctly pass parameters; parameters must be passed using only numbers, e.g. $2 or $4.".format(command))
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
						raise ConfigValidationError("server_bots", "execute line for command {} escapes the end of the string".format(command))
					if previousWasDollar:
						raise ConfigValidationError("server_bots", "execute line for command {} terminates with an incomplete parameter replacement".format(command))
				if "help_command" in commandData:
					if not isinstance(commandData["help_command"], bool):
						raise ConfigValidationError("server_bots", "help_command value for command {} must be boolean".format(command))
				else:
					commandData["help_command"] = False
				if "execute" not in commandData and not commandData["help_command"]:
					raise ConfigValidationError("server_bots", "the command {} doesn't do anything!".format(command))
				if "respond_privmsg" in commandData:
					if not isinstance(commandData["respond_privmsg"], bool):
						raise ConfigValidationError("server_bots", "respond_privmsg value for command {} must be boolean".format(command))
				else:
					commandData["respond_privmsg"] = True
				if "respond_notice" in commandData:
					if not isinstance(commandData["respond_notice"], bool):
						raise ConfigValidationError("server_bots", "respond_notice value for command {} must be boolean".format(command))
				else:
					commandData["respond_notice"] = False
				if not commandData["respond_privmsg"] and not commandData["respond_notice"]:
					raise ConfigValidationError("server_bots", "command {} will never be run!".format(command))
	
	def receiveBotMessageProcessor(self, botConfig: Dict[str, Any]) -> None:
		def receiveBotMessage(botUser: LocalUser, command: str, *args: str, **kw: Any) -> None:
			if command not in ("PRIVMSG", "NOTICE"):
				return
			if "to" in kw and kw["to"] != botUser.nick:
				return # Ignore potential channel messages or any other crap we might pick up
			if "prefix" not in kw:
				return
			prefix = kw["prefix"]
			if prefix in self.ircd.serverNames:
				return # Ignore messages and notices from servers
			if "!" in prefix:
				fromNick = prefix.split("!", 1)[0]
			elif "@" in prefix:
				fromNick = prefix.split("@", 1)[0]
			else:
				fromNick = prefix
			if fromNick not in self.ircd.userNicks:
				return
			fromUser = self.ircd.userNicks[fromNick]
			message = args[0]
			messageParts = message.split(" ")
			command = messageParts.pop(0)
			command = command.upper()
			if command not in botConfig["commands"]:
				fromUser.sendMessage("NOTICE", "Unknown command \x02{}".format(command), prefix=botUser.hostmask())
				return
			if len(messageParts) == 1 and not messageParts[0]:
				messageParts = []
			commandData = botConfig["commands"][command]
			if command == "PRIVMSG" and not commandData["respond_privmsg"]:
				return
			if command == "NOTICE" and not commandData["respond_notice"]:
				return
			if commandData["help_command"]:
				if messageParts and messageParts[0]:
					whichCommand = messageParts[0].upper()
					if whichCommand not in botConfig["commands"]:
						fromUser.sendMessage("NOTICE", "No such command \x02{}".format(whichCommand), prefix=botUser.hostmask())
						return
					helpText = "\n".join(botConfig["commands"][whichCommand]["detailed_help"])
					helpTextChunks = splitMessage(helpText, 100)
					botHostmask = botUser.hostmask()
					fromUser.sendMessage("NOTICE", "Help for command \x02{}".format(whichCommand), prefix=botHostmask)
					for helpLine in helpTextChunks:
						fromUser.sendMessage("NOTICE", helpLine, prefix=botHostmask, alwaysPrefixLastParam=True)
					fromUser.sendMessage("NOTICE", "End of help for command \x02{}".format(whichCommand), prefix=botHostmask)
					return
				helpIntroTextLines = botConfig["help_intro"]
				helpIntroText = "\n".join(helpIntroTextLines)
				helpIntroTextChunks = splitMessage(helpIntroText, 100)
				botHostmask = botUser.hostmask()
				for helpLine in helpIntroTextChunks:
					fromUser.sendMessage("NOTICE", helpLine, prefix=botHostmask, alwaysPrefixLastParam=True)
				for helpCommand, helpCommandData in botConfig["commands"].items():
					fromUser.sendMessage("NOTICE", "  \x02{}\x02 - {}".format(helpCommand, helpCommandData["help"]), prefix=botHostmask)
				fromUser.sendMessage("NOTICE", "End of help", prefix=botHostmask)
				return
			commandLineToRun = commandData["execute"]
			if " " in commandLineToRun:
				commandToRun, commandParamStr = commandLineToRun.split(" ", 1)
			else:
				commandToRun = commandLineToRun
				commandParamStr = ""
			
			if commandToRun not in self.ircd.userCommands:
				fromUser.sendMessage("NOTICE", "No such command \x02{}".format(command), prefix=botUser.hostmask())
				return
			
			assembledParams = []
			escaped = False
			readingVariable = False
			variableParameterData = []
			for paramChar in commandParamStr:
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
						assembledParams.append(" ".join(args[startingParamNumber:]))
						continue
					if startingParamNumber >= 0 and startingParamNumber < len(args):
						assembledParams.append(args[startingParamNumber])
				if paramChar == "$":
					readingVariable = True
					continue
				if paramChar == "\\":
					escaped = True
					continue
				assembledParams.append(paramChar)
			if readingVariable:
				startingParamNumber = int("".join(variableParameterData)) - 1
				if startingParamNumber < len(args):
					assembledParams.append(args[startingParamNumber])
			
			paramsString = "".join(assembledParams)
			lastParam = None
			if " :" in paramsString:
				paramsString, lastParam = paramsString.split(" :", 1)
			params = paramsString.split(" ")
			if lastParam is not None:
				params.append(lastParam)
			fromUser.handleCommand(commandToRun, params, "", {})
		return receiveBotMessage

serverBots = ServerBots()