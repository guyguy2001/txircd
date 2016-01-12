from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import isValidMetadataKey
from zope.interface import implements

irc.RPL_WHOISKEYVALUE = "760"
irc.RPL_KEYVALUE = "761"
irc.RPL_METADATAEND = "762"
irc.ERR_METADATALIMIT = "764"
irc.ERR_TARGETINVALID = "765"
irc.ERR_NOMATCHINGKEY = "766"
irc.ERR_KEYINVALID = "767"
irc.ERR_KEYNOTSET = "768"
irc.ERR_KEYNOPERMISSION = "769"

class Metadata(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "Metadata"
	
	def actions(self):
		return [ ("buildisupport", 10, self.addToISupport) ]
	
	def userCommands(self):
		return [ ("METADATA", 1, self) ]
	
	def verifyConfig(self, config):
		if "metadata_limit" in config:
			if config["metadata_limit"] is not None and (not isinstance(config["metadata_limit"], int) or config["metadata_limit"] < 0):
				raise ConfigValidationError("metadata_limit", "invalid number and not null value")
		else:
			config["metadata_limit"] = None
	
	def addToISupport(self, iSupportList):
		iSupportList["METADATA"] = self.ircd.config["metadata_limit"]
	
	def parseParams(self, user, params, prefix, tags):
		paramCount = len(params)
		if paramCount < 2:
			user.sendSingleError("MetadataParams", irc.ERR_NEEDMOREPARAMS, "METADATA", "Not enough parameters")
			return None
		target = params[0]
		subcmd = params[1].upper()
		if subcmd not in ("GET", "SET", "LIST", "CLEAR"):
			user.sendSingleError("MetadataParams", irc.ERR_UNKNOWNCOMMAND, "METADATA", "Invalid subcommand")
			return None
		targetIsChannel = False
		if target == "*":
			targetUser = user
		elif target in self.ircd.userNicks:
			targetUser = self.ircd.users[self.ircd.userNicks[target]]
		elif target in self.ircd.channels:
			targetIsChannel = True
			targetChannel = self.ircd.channels[target]
		else:
			user.sendSingleError("MetadataParams", irc.ERR_TARGETINVALID, target, "invalid metadata target")
		if subcmd == "GET":
			if paramCount < 3:
				user.sendSingleError("MetadataParams", irc.ERR_NEEDMOREPARAMS, "METADATA", "Not enough parameters")
				return None
			if targetIsChannel:
				return {
					"subcmd": "GET",
					"targetchan": targetChannel,
					"keys": params[2:]
				}
			return {
				"subcmd": "GET",
				"targetuser": targetUser,
				"keys": params[2:]
			}
		if subcmd == "SET":
			if paramCount < 3:
				user.sendSingleError("MetadataParams", irc.ERR_NEEDMOREPARAMS, "METADATA", "Not enough parameters")
				return None
			data = {
				"subcmd": "SET",
				"key": params[2]
			}
			if targetIsChannel:
				data["targetchan"] = targetChannel
			else:
				data["targetuser"] = targetUser
			if paramCount > 3:
				data["value"] = params[3]
			return data
		if targetIsChannel:
			return {
				"subcmd": subcmd,
				"targetchan": targetChannel
			}
		return {
			"subcmd": subcmd,
			"targetuser": targetUser
		}
	
	def affectedChannels(self, user, data):
		if "targetchan" in data:
			return [data["targetchan"]]
	
	def execute(self, user, data):
		if "targetuser" in data:
			target = data["targetuser"]
			if target == user:
				targetName = "*"
			else:
				targetName = target.nick
		elif "targetchan" in data:
			target = data["targetchan"]
			targetName = target.name
		else:
			return None
		
		subcmd = data["subcmd"]
		if subcmd == "LIST":
			metadataList = target.metadataList()
			for key, value, visibility, setByUser in metadataList:
				if user.canSeeMetadataVisibility(visibility):
					user.sendMessage(irc.RPL_KEYVALUE, targetName, key, visibility, value)
			user.sendMessage(irc.RPL_METADATAEND, "end of metadata")
			return True
		if subcmd == "CLEAR":
			if target != user and not self.ircd.runActionUntilValue("metadatasetpermission", user, target, "*"):
				user.sendMessage(irc.ERR_KEYNOPERMISSION, targetName, "*", "permission denied")
				return True
			metadataList = target.metadataList()
			for key, value, visibility, setByUser in metadataList:
				if not user.canSeeMetadataVisibility(visibility):
					continue
				if target.setMetadata(key, None, visibility, True):
					user.sendMessage(irc.RPL_KEYVALUE, targetName, key, visibility)
				else:
					user.sendMessage(irc.ERR_KEYNOPERMISSION, targetName, key, "permission denied")
			user.sendMessage(irc.RPL_METADATAEND, "end of metadata")
			return True
		if subcmd == "GET":
			keyList = data["keys"]
			for key in keyList:
				if not isValidMetadataKey(key):
					user.sendMessage(irc.ERR_KEYINVALID, key, "invalid metadata key")
					continue
				if not target.metadataKeyExists(key):
					user.sendMessage(irc.ERR_NOMATCHINGKEY, targetName, key, "no matching key")
					continue
				realKey = target.metadataKeyCase(key)
				visibility = target.metadataVisibility(key)
				if not user.canSeeMetadataVisibility(visibility):
					user.sendMessage(irc.ERR_KEYNOPERMISSION, targetName, realKey, "permission denied")
					continue
				value = target.metadataValue(key)
				user.sendMessage(irc.RPL_KEYVALUE, targetName, realKey, visibility, value)
			return True
		if subcmd == "SET":
			key = data["key"]
			if not isValidMetadataKey(key):
				user.sendMessage(irc.ERR_KEYINVALID, key, "invalid metadata key")
				return True
			if target != user and not self.ircd.runActionUntilValue("metadatasetpermission", user, target, "*"):
				user.sendMessage(irc.ERR_KEYNOPERMISSION, targetName, key, "permission denied")
				return True
			visibility = self.ircd.runActionUntilValue("metadatavisibility", key)
			if visibility is None:
				visibility = "*"
			if not user.canSeeMetadataVisibility(visibility):
				user.sendMessage(irc.ERR_KEYNOPERMISSION, targetName, key, "permission denied")
				return True
			alreadySet = 0
			for metadataData in target.metadataList():
				if metadataData[3]:
					alreadySet += 1
			if alreadySet >= self.ircd.config["metadata_limit"]:
				user.sendMessage(irc.ERR_METADATALIMIT, targetName, "metadata limit reached")
				return True
			value = data["value"] if "value" in data else None
			if target.setMetadata(key, value, visibility, True):
				if value is None:
					user.sendMessage(irc.RPL_KEYVALUE, targetName, key, visibility)
				else:
					user.sendMessage(irc.RPL_KEYVALUE, targetName, key, visibility, value)
				user.sendMessage(irc.RPL_METADATAEND, "end of metadata")
			else:
				user.sendMessage(irc.ERR_KEYNOTSET, targetName, key, "key not set")
			return True
		return None

metadata = Metadata()