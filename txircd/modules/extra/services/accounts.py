from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, ircLower, isValidNick, lenBytes, now, timestamp, timestampStringFromTime, timestampStringFromTimestamp
from zope.interface import implementer
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from validate_email import validate_email as validateEmail
from weakref import WeakSet

accountFormatVersion = "0"

@implementer(IPlugin, IModuleData)
class Accounts(ModuleData):
	name = "Accounts"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("updatestoragereferences", 10, self.setStorageReferences),
			("createnewaccount", 1, self.createAccount),
			("accountsetupindices", 100, self.indexAccount),
			("accountremoveindices", 100, self.unindexAccount),
			("accountauthenticate", 1, self.authenticateUser),
			("accountlogout", 1, self.logUserOut),
			("deleteaccount", 1, self.deleteAccount),
			("accountchangename", 1, self.changeAccountName),
			("accountchangepass", 1, self.setPassword),
			("accountchangeemail", 1, self.setEmail),
			("accountaddnick", 1, self.addAltNick),
			("accountremovenick", 1, self.removeAltNick),
			("accountsetmetadata", 1, self.setMetadata),
			("accountlistallnames", 1, self.allAccountNames),
			("accountlistnicks", 1, self.accountNicks),
			("accountgetemail", 1, self.getEmail),
			("accountgetregtime", 1, self.getRegTime),
			("accountgetlastlogin", 1, self.getLastLogin),
			("accountgetusers", 1, self.getAccountUsers),
			("accountfromnick", 1, self.getAccountFromNick),
			("accountgetmetadatakeyexists", 1, self.getMetadataKeyExists),
			("accountgetmetadatavalue", 1, self.getMetadataValue),
			("checkaccountexists", 1, self.checkAccountExistence),
			("usermetadataupdate", 10, self.updateLastLoginTime),
			("usermetadataupdate", 1, self.updateLoggedInUsers),
			("burst", 5, self.startBurst) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("ACCOUNTINFO", 1, AccountInfoCommand(self)),
			("CREATEACCOUNT", 1, CreateAccountCommand(self)),
			("DELETEACCOUNT", 1, DeleteAccountCommand(self)),
			("UPDATEACCOUNTNAME", 1, UpdateAccountNameCommand(self)),
			("UPDATEACCOUNTPASS", 1, UpdateAccountPassCommand(self)),
			("UPDATEACCOUNTEMAIL", 1, UpdateAccountEmailCommand(self)),
			("ADDACCOUNTNICK", 1, AddAccountNickCommand(self)),
			("REMOVEACCOUNTNICK", 1, RemoveAccountNickCommand(self)),
			("SETACCOUNTMETADATA", 1, SetAccountMetadataCommand(self)),
			("ACCOUNTBURSTINIT", 1, AccountBurstInitCommand(self)) ]
	
	def load(self) -> None:
		if "services" not in self.ircd.storage:
			self.ircd.storage["services"] = {}
		if "accounts" not in self.ircd.storage["services"]:
			self.ircd.storage["services"]["accounts"] = {}
			self.ircd.storage["services"]["accounts"]["data"] = {}
			self.ircd.storage["services"]["accounts"]["index"] = {}
			self.ircd.storage["services"]["accounts"]["deleted"] = {}
		self.loggedInUsers = CaseInsensitiveDictionary()
		self.setStorageReferences()
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "account_password_hash" not in config or not config["account_password_hash"]:
			raise ConfigValidationError("account_password_hash", "A password hash must be defined for accounts to work.")
		if "account_password_minimum_length" not in config or not config["account_password_minimum_length"]:
			config["account_password_minimum_length"] = 10
		if not isinstance(config["account_password_minimum_length"], int) or config["account_password_minimum_length"] < 1:
			raise ConfigValidationError("account_password_minimum_length", "invalid number")
		if "account_require_email" not in config:
			config["account_require_email"] = False
		if not isinstance(config["account_require_email"], bool):
			raise ConfigValidationError("account_require_email", "must be true or false")
		if "account_max_nicks" in config:
			if not isinstance(config["account_max_nicks"], int) or config["account_max_nicks"] < 1:
				raise ConfigValidationError("account_max_nicks", "invalid number")
	
	def setStorageReferences(self) -> None:
		self.servicesData = self.ircd.storage["services"]
		self.accountData = self.servicesData["accounts"]
	
	def registerAccountFromInfo(self, accountInfo: Dict[str, Any], updateConflictingIfTied: bool, fromServer: "IRCServer") -> bool:
		"""
		Registers the given account if it has the minimum required data.
		If the account already exists, replaces that account if the timestamp is less.
		In the case of a tie, non-conflicting data (nickname list) is updated. Conflicting data is also updated if updateConflictingIfTied is true.
		This function is meant to accommodate server commands, so fromServer must be passed.
		"""
		if "username" not in accountInfo or "password" not in accountInfo or "nick" not in accountInfo: # We need to do some basic sanity checks. This data is required.
			return False
		nearestFromServer = fromServer
		while nearestFromServer.nextClosest != self.ircd.serverID:
			nearestFromServer = self.ircd.servers[nearestFromServer.nextClosest]
		accountName = accountInfo["username"]
		lowerAccountName = ircLower(accountName)
		accountNicks = accountInfo["nick"]
		accountTime = accountInfo["registered"]
		conflictNicks = []
		shouldRegisterAccount = True
		
		if "nick" not in self.accountData["index"]:
			self.accountData["index"]["nick"] = {}
		
		for nickData in accountNicks:
			if nickData[0] == accountName:
				break
		else: # Account name must be in nickname list for basic account consistency
			return False
		otherAccountData = None
		if lowerAccountName in self.accountData["data"]:
			otherAccountData = self.accountData["data"][lowerAccountName]
			if accountTime > otherAccountData["registered"]:
				shouldRegisterAccount = False
			if accountTime < otherAccountData["registered"]:
				self.deleteAccount(accountName, nearestFromServer)
		for nickData in accountNicks:
			if ircLower(nickData[0]) in self.accountData["index"]["nick"]:
				conflictNicks.append(nickData)
		if conflictNicks:
			for nickData in conflictNicks:
				lowerNick = ircLower(nickData[0])
				otherLowerAccountName = self.accountData["index"]["nick"][lowerNick]
				otherNickData = None
				for otherAccountNickData in self.accountData["data"][otherLowerAccountName]["nick"]:
					if ircLower(otherAccountNickData[0]) == lowerNick:
						otherNickData = otherAccountNickData
						break
				else:
					continue
				nickIsAccount = (lowerNick == lowerAccountName)
				otherNickIsAccount = (lowerNick == otherLowerAccountName)
				if nickData[1] == otherNickData[1]:
					if nickIsAccount and otherNickIsAccount:
						continue # We'll handle merging accounts as part of registering this one
					if nickIsAccount:
						self.deleteAccount(otherLowerAccountName, nearestFromServer)
					elif otherNickIsAccount:
						return False
					else:
						accountNicks.remove(nickData)
						self.removeAltNick(otherLowerAccountName, otherNickData[0], nearestFromServer)
				elif nickData[1] < otherNickData[1]:
					if otherNickIsAccount:
						self.deleteAccount(otherLowerAccountName, nearestFromServer)
					else:
						self.removeAltNick(otherLowerAccountName, otherNickData[0], nearestFromServer)
				else:
					if nickIsAccount:
						return False
					accountNicks.remove(nickData)
		if not shouldRegisterAccount:
			return False
		if otherAccountData is None:
			self.accountData["data"][lowerAccountName] = accountInfo
			self.ircd.runActionStandard("accountsetupindices", accountName)
			return True
		self.ircd.runActionStandard("accountremoveindices", accountName)
		existingNicks = {}
		for otherNickData in otherAccountData["nick"]:
			existingNicks[ircLower(otherNickData[0])] = otherNickData[1]
		for nickData in accountNicks:
			lowerNick = ircLower(nickData[0])
			if lowerNick in existingNicks:
				if nickData[1] < existingNicks[lowerNick]:
					for otherNickData in otherAccountData["nick"]:
						if ircLower(otherNickData[0]) == lowerNick:
							otherNickData[1] = nickData[1]
							break
		if updateConflictingIfTied:
			accountInfo["nick"] = otherAccountData["nick"]
			self.accountData["data"][lowerAccountName] = accountInfo
		self.ircd.runActionStandard("accountsetupindices", accountName)
		return True
	
	def createAccount(self, username: str, password: str, passwordHashedMethod: str, email: str, user: Optional["IRCUser"], fromServer: "IRCServer" = None) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Creates a new services account.
		Requires a username and password to be entered.
		If passwordHashedMethod is None, assumes an unhashed password is passed in. We'll hash it for you.
		Otherwise, the password is already hashed with the entered hash method, and that hash method module must be loaded.
		An email address is optional here, but one may be required by other modules.
		Returns (True, None, None) if account creation succeeds. Returns (False, "ERRCODE", "error message") otherwise.
		"""
		if not username:
			return False, "BADPARAM", "No username entered."
		if not password:
			return False, "BADPARAM", "No password entered."
		if passwordHashedMethod is None and len(password) < self.ircd.config["account_password_minimum_length"]:
			return False, "BADPASS", "Password is not at least {} characters long.".format(self.ircd.config["account_password_minimum_length"])
		
		if email:
			if not validateEmail(email):
				return False, "INVALIDEMAIL", "The provided email address is in an invalid format."
			if "email" not in self.accountData["index"]:
				self.accountData["index"]["email"] = {}
			if email in self.accountData["index"]["email"]:
				return False, "DUPEMAIL", "That email address is already used by another account."
		elif self.ircd.config["account_require_email"]:
			return False, "EMAILREQUIRED", "An email address is required but was not provided."
		
		if not isValidNick(username) or lenBytes(username) > self.ircd.config.get("nick_length", 32):
			return False, "INVALIDUSERNAME", "The username is not a valid nickname"
		
		lowerUsername = ircLower(username)
		if lowerUsername in self.accountData["data"]:
			return False, "DUPNAME", "An account with that name already exists."
		if "nick" not in self.accountData["index"]:
			self.accountData["index"]["nick"] = {}
		if lowerUsername in self.accountData["index"]["nick"]:
			return False, "DUPNICK", "That nickname is already in use on a different account."
		
		if passwordHashedMethod is None:
			passwordHashMethod = self.ircd.config["account_password_hash"]
			if "hash-{}".format(passwordHashMethod) not in self.ircd.functionCache:
				return False, "BADHASH", "Can't hash password with configured hash method."
			hashedPassword = self.ircd.functionCache["hash-{}".format(passwordHashMethod)](password)
		else:
			if "compare-{}".format(passwordHashedMethod) not in self.ircd.functionCache:
				return False, "BADHASH", "Provided hash method isn't loaded."
			passwordHashMethod = passwordHashedMethod
			hashedPassword = password
		
		registrationTime = now()
		newAccountInfo = {}
		newAccountInfo["username"] = username
		newAccountInfo["password"] = hashedPassword
		newAccountInfo["password-hash"] = passwordHashMethod
		newAccountInfo["nick"] = [(username, registrationTime)]
		if email:
			newAccountInfo["email"] = email
		if "registered" not in newAccountInfo:
			newAccountInfo["registered"] = registrationTime
		newAccountInfo["settings"] = {}
		newAccountInfo["metadata"] = {}
		
		self.accountData["data"][lowerUsername] = newAccountInfo
		if lowerUsername in self.accountData["deleted"]:
			del self.accountData["deleted"][lowerUsername]
		
		self.ircd.runActionStandard("accountsetupindices", username)
		
		serializedAccountInfo = serializeAccount(newAccountInfo)
		self.ircd.broadcastToServers(fromServer, "CREATEACCOUNT", timestampStringFromTime(registrationTime), serializedAccountInfo, prefix=self.ircd.serverID)
		if user and user.uuid[:3] == self.ircd.serverID:
			user.setMetadata("account", username)
		
		self.ircd.runActionStandard("accountcreated", username)
		return True, None, None
	
	def indexAccount(self, accountName: str) -> None:
		"""
		Used only by other account action implementing functions to index account information.
		Call this after changing account information.
		"""
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.accountData["data"]:
			return
		if "nick" not in self.accountData["index"]:
			self.accountData["index"]["nick"] = {}
		for accountNickData in self.accountData["data"][lowerAccountName]["nick"]:
			self.accountData["index"]["nick"][ircLower(accountNickData[0])] = lowerAccountName
		if "email" not in self.accountData["index"]:
			self.accountData["index"]["email"] = {}
		if "email" in self.accountData["data"][lowerAccountName]:
			self.accountData["index"]["email"][self.accountData["data"][lowerAccountName]["email"]] = lowerAccountName
	
	def unindexAccount(self, accountName: str) -> None:
		"""
		Used only by other account action implementing functions to unindex account information.
		Call this before changing account information.
		"""
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.accountData["data"]:
			return
		for accountNickData in self.accountData["data"][lowerAccountName]["nick"]:
			lowerAccountNick = ircLower(accountNickData[0])
			if lowerAccountNick in self.accountData["index"]["nick"] and self.accountData["index"]["nick"][lowerAccountNick] == lowerAccountName:
				del self.accountData["index"]["nick"][lowerAccountNick]
		if "email" in self.accountData["data"][lowerAccountName]:
			emailAddr = self.accountData["data"][lowerAccountName]["email"]
			if self.accountData["index"]["email"][emailAddr] == lowerAccountName:
				del self.accountData["index"]["email"][emailAddr]
	
	def authenticateUser(self, user: "IRCUser", username: str, password: str, completeLogin: bool = True) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Authenticates a user for an account.
		Accepts a username (or, for other functions implementing this action, another unique piece of account information)
		and password, and it checks whether the user is allowed to be signed into that account.
		Returns False, "code", "message" if the login failed.
		Returns True, None, None, if the login succeeded.
		If further processing is needed to determine, returns None, Deferred, None. A callback accepting three parameters
		(one for each return value) can be added to the Deferred to handle the result of the authentication.
		"""
		if not username:
			return False, "BADPARAM", "No username entered."
		if not password:
			return False, "BADPARAM", "No password entered."
		lowerUsername = ircLower(username)
		if lowerUsername not in self.accountData["data"]:
			return False, "NOTEXIST", "Account does not exist."
		hashedAccountPassword = self.accountData["data"][lowerUsername]["password"]
		
		passwordHashMethod = self.accountData["data"][lowerUsername]["password-hash"]
		if "compare-{}".format(passwordHashMethod) not in self.ircd.functionCache:
			return False, "BADHASH", "Could not verify password"
		if not self.ircd.functionCache["compare-{}".format(passwordHashMethod)](password, hashedAccountPassword):
			return False, "WRONG", "Login credentials were incorrect."
		
		loginExtraCheckResult = self.ircd.runActionUntilValue("accountloginextracheck", user, lowerUsername, users=[user])
		if loginExtraCheckResult and not loginExtraCheckResult[0]:
			return loginExtraCheckResult
		
		if completeLogin:
			username = self.accountData["data"][lowerUsername]["username"]
			user.setMetadata("account", username)
		return True, None, None
	
	def updateLastLoginTime(self, user: "IRCUser", key: str, oldValue: str, value: str, fromServer: "IRCServer" = None) -> None:
		if key != "account":
			return
		if value is None:
			return # This doesn't apply for users logging out
		lowerAccountName = ircLower(value)
		if lowerAccountName not in self.accountData["data"]:
			return
		self.accountData["data"][lowerAccountName]["lastlogin"] = now()
	
	def logUserOut(self, user: "IRCUser") -> bool:
		"""
		Logs a user out of the account into which they are logged.
		"""
		user.setMetadata("account", None)
		return True
	
	def deleteAccount(self, username: str, fromServer: "IRCServer" = None) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Deletes an account.
		"""
		lowerUsername = ircLower(username)
		if lowerUsername not in self.accountData["data"]:
			return False, "NOTEXIST", "Account not registered."
		self.ircd.runActionStandard("accountremoveindices", lowerUsername)
		username = self.accountData["data"][lowerUsername]["username"]
		for user in self.ircd.users.values():
			if user.metadataValue("account") == username:
				self.ircd.runActionStandard("accountlogout", user)
		createTime = self.accountData["data"][lowerUsername]["registered"]
		
		deleteTime = now()
		del self.accountData["data"][lowerUsername]
		self.accountData["deleted"][lowerUsername] = { "deleted": deleteTime, "created": createTime }
		self.ircd.broadcastToServers(fromServer, "DELETEACCOUNT", timestampStringFromTime(deleteTime), username, timestampStringFromTime(createTime), prefix=self.ircd.serverID)
		for user in self.ircd.users.values():
			if user.metadataKeyExists("account") and ircLower(user.metadataValue("account")) == lowerUsername:
				user.setMetadata("account", None)
		self.ircd.runActionStandard("handledeleteaccount", username)
		return True, None, None
	
	def changeAccountName(self, oldAccountName: str, newAccountName: str, fromServer: "IRCServer" = None) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Changes the account name for an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		lowerOldAccountName = ircLower(oldAccountName)
		
		if lowerOldAccountName not in self.accountData["data"]:
			return False, "BADACCOUNT", "The account does not exist."
		
		if not isValidNick(newAccountName) or lenBytes(newAccountName) > self.ircd.config.get("nick_length", 32):
			return False, "BADUSER", "The username is not a valid nickname"
		
		lowerNewAccountName = ircLower(newAccountName)
		for nickData in self.accountData["data"][lowerOldAccountName]["nick"]:
			if lowerNewAccountName == ircLower(nickData[0]):
				newAccountName = nickData[0]
				break
		else:
			return False, "NONICKLINK", "The new account name isn't associated with the account. The new account name should be grouped with the existing account as an alternate nickname."
		self.ircd.runActionStandard("accountremoveindices", oldAccountName)
		accountInfo = self.accountData["data"][lowerOldAccountName]
		del self.accountData["data"][lowerOldAccountName]
		accountInfo["username"] = newAccountName
		registerTime = accountInfo["registered"]
		updateTime = now()
		if "oldnames" not in accountInfo:
			accountInfo["oldnames"] = []
		accountInfo["oldnames"].append((oldAccountName, updateTime))
		oldAccountName = accountInfo["username"]
		accountInfo["username"] = newAccountName
		self.accountData["data"][lowerNewAccountName] = accountInfo
		self.ircd.runActionStandard("accountsetupindices", newAccountName)
		self.ircd.broadcastToServers(fromServer, "UPDATEACCOUNTNAME", timestampStringFromTime(updateTime), oldAccountName, timestampStringFromTimestamp(registerTime), newAccountName, prefix=self.ircd.serverID)
		if not fromServer:
			for user in self.ircd.users.values():
				if user.metadataKeyExists("account") and ircLower(user.metadataValue("account")) == lowerOldAccountName:
					user.setMetadata("account", newAccountName)
		self.ircd.runActionStandard("handleaccountchangename", oldAccountName, newAccountName)
		return True, None, None
	
	def setPassword(self, accountName: str, password: str, hashMethod: str, fromServer: "IRCServer" = None) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Set the password for an account.
		For plain passwords, the hashMethod is None.
		If it's not, the password must be hashed with that hash method, and the hash method module must be loaded.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.accountData["data"]:
			return False, "BADACCOUNT", "The account does not exist."
		
		if hashMethod is None:
			hashMethod = self.ircd.config["account_password_hash"]
			if "hash-{}".format(hashMethod) not in self.ircd.functionCache:
				return False, "BADHASH", "Can't hash password with the configured hash method."
			hashedPassword = self.ircd.functionCache["hash-{}".format(hashMethod)](password)
		else:
			if "compare-{}".format(hashMethod) not in self.ircd.functionCache:
				return False, "BADHASH", "Provided hash method isn't loaded."
			hashedPassword = password
		self.accountData["data"][lowerAccountName]["password"] = hashedPassword
		self.accountData["data"][lowerAccountName]["password-hash"] = hashMethod
		updateTime = now()
		registerTime = self.accountData["data"][lowerAccountName]["registered"]
		self.ircd.broadcastToServers(fromServer, "UPDATEACCOUNTPASS", timestampStringFromTime(updateTime), accountName, timestampStringFromTime(registerTime), hashedPassword, hashMethod, prefix=self.ircd.serverID)
		return True, None, None
	
	def setEmail(self, accountName: str, email: str, fromServer: "IRCServer" = None) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Sets the email address for an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.accountData["data"]:
			return False, "BADACCOUNT", "The account does not exist."
		if not email and self.ircd.config["account_require_email"]:
			return False, "EMAILREQUIRED", "An email address is required, so the email address associated with this account cannot be removed."
		if email and not validateEmail(email):
			return False, "BADEMAIL", "The provided email address is invalid."
		
		self.ircd.runActionStandard("accountremoveindices", accountName)
		if email:
			self.accountData["data"][lowerAccountName]["email"] = email
		elif "email" in self.accountData["data"][lowerAccountName]:
			del self.accountData["data"][lowerAccountName]["email"]
		updateTime = now()
		registerTime = self.accountData["data"][lowerAccountName]["registered"]
		self.ircd.broadcastToServers(fromServer, "UPDATEACCOUNTEMAIL", timestampStringFromTime(updateTime), accountName, timestampStringFromTime(registerTime), email, prefix=self.ircd.serverID)
		self.ircd.runActionStandard("accountsetupindices", accountName)
		return True, None, None
	
	def addAltNick(self, accountName: str, newNick: str, fromServer: "IRCServer" = None) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Adds a nickname to an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.accountData["data"]:
			return False, "BADACCOUNT", "The account does not exist."
		
		lowerNewNick = ircLower(newNick)
		if lowerNewNick in self.accountData["index"]["nick"]:
			if self.accountData["index"]["nick"][lowerNewNick] == lowerAccountName:
				return False, "NICKALREADYLINKED", "That nickname is already associated with your account."
			return False, "NICKINUSE", "That nickname is already associated with a different account."
		
		maxNicks = self.ircd.config.get("account_max_nicks", None)
		if maxNicks is not None and len(self.accountData["data"][lowerAccountName]["nick"]) >= maxNicks:
			return False, "LIMITREACHED", "The maximum number of allowable nicknames is already registered to your account."
		
		self.ircd.runActionStandard("accountremoveindices", accountName)
		
		addTime = now()
		self.accountData["data"][lowerAccountName]["nick"].append((newNick, addTime))
		registerTime = self.accountData["data"][lowerAccountName]["registered"]
		self.ircd.broadcastToServers(fromServer, "ADDACCOUNTNICK", timestampStringFromTime(addTime), accountName, timestampStringFromTime(registerTime), newNick, prefix=self.ircd.serverID)
		self.ircd.runActionStandard("accountsetupindices", accountName)
		return True, None, None
	
	def removeAltNick(self, accountName: str, oldNick: str, fromServer: "IRCServer" = None) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Removes a nickname from an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.accountData["data"]:
			return False, "BADACCOUNT", "The account does not exist."
		
		lowerOldNick = ircLower(oldNick)
		if lowerOldNick == lowerAccountName:
			return False, "NICKISACCOUNT", "That nickname is the primary nickname of the account."
		if lowerOldNick not in self.accountData["index"]["nick"]:
			return False, "NICKNOLINK", "That nickname is not associated with an account."
		if self.accountData["index"]["nick"][lowerOldNick] != lowerAccountName:
			return False, "NICKINUSE", "That nickname is associated with a different account."
		self.ircd.runActionStandard("accountremoveindices", accountName)
		for index, nickData in enumerate(self.accountData["data"][lowerAccountName]["nick"]):
			if ircLower(nickData[0]) == lowerOldNick:
				del self.accountData["data"][lowerAccountName]["nick"][index]
				break
		removeTime = now()
		registerTime = self.accountData["data"][lowerAccountName]["registered"]
		self.ircd.broadcastToServers(fromServer, "REMOVEACCOUNTNICK", timestampStringFromTime(removeTime), accountName, timestampStringFromTime(registerTime), oldNick, prefix=self.ircd.serverID)
		self.ircd.runActionStandard("accountsetupindices", accountName)
		return True, None, None
	
	def setMetadata(self, accountName: str, key: str, value: Optional[str], fromServer: "IRCServer" = None) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, "Deferred", None]]:
		"""
		Sets metadata for an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.accountData["data"]:
			return False, "BADACCOUNT", "The account does not exist"
		
		extraCheckResult = self.ircd.runActionUntilValue("accountsetmetadataextracheck", accountName, key, value)
		if extraCheckResult and not extraCheckResult[0]:
			return extraCheckResult
		
		self.ircd.runActionStandard("accountremoveindices", accountName)
		if value is None:
			del self.accountData["data"][lowerAccountName]["metadata"][key]
		else:
			self.accountData["data"][lowerAccountName]["metadata"][key] = value
		setTime = now()
		registerTime = self.accountData["data"][lowerAccountName]["registered"]
		if value is None:
			self.ircd.broadcastToServers(fromServer, "SETACCOUNTMETADATA", timestampStringFromTime(setTime), accountName, timestampStringFromTime(registerTime), key, prefix=self.ircd.serverID)
		else:
			self.ircd.broadcastToServers(fromServer, "SETACCOUNTMETADATA", timestampStringFromTime(setTime), accountName, timestampStringFromTime(registerTime), key, value, prefix=self.ircd.serverID)
		self.ircd.runActionStandard("accountsetupindices", accountName)
		return True, None, None
	
	def allAccountNames(self) -> List[str]:
		"""
		Returns a list of all registered account names.
		"""
		return list(self.accountData["data"].keys())
	
	def accountNicks(self, accountName: str) -> Optional[List[str]]:
		"""
		Returns all nicknames associated with the account.
		If the account doesn't exist, returns None.
		"""
		try:
			return self.accountData["data"][ircLower(accountName)]["nick"]
		except KeyError:
			return None
	
	def getEmail(self, accountName: str) -> Optional[str]:
		"""
		Returns the email address associated with an account, if populated.
		"""
		try:
			return self.accountData["data"][ircLower(accountName)]["email"]
		except KeyError:
			return None
	
	def getRegTime(self, accountName: str) -> Optional[datetime]:
		"""
		Returns the registration time for a user.
		"""
		try:
			return self.accountData["data"][ircLower(accountName)]["registered"]
		except KeyError:
			return None
	
	def getLastLogin(self, accountName: str) -> Optional[datetime]:
		"""
		Returns the last login time for a user.
		"""
		try:
			return self.accountData["data"][ircLower(accountName)]["lastlogin"]
		except KeyError:
			return None
	
	def getAccountUsers(self, accountName: str) -> Optional[List["IRCUser"]]:
		"""
		Returns a list of currently logged-in users for an account.
		"""
		if accountName in self.loggedInUsers:
			return list(self.loggedInUsers[accountName])
		return None
	
	def getAccountFromNick(self, nick: str) -> Optional[str]:
		"""
		Returns an account name from the given nickname.
		Returns None if the nickname isn't grouped with an account.
		"""
		lowerNickname = ircLower(nick)
		if "nick" not in self.accountData["index"]:
			return None
		if lowerNickname not in self.accountData["index"]["nick"]:
			return None
		lowerAccountName = self.accountData["index"]["nick"][lowerNickname]
		return self.accountData["data"][lowerAccountName]["username"]
	
	def getMetadataKeyExists(self, accountName: str, key: str) -> Optional[bool]:
		"""
		Returns whether the given metadata key exists for the given account.
		Returns None if the given account doesn't exist.
		"""
		try:
			if key in self.accountData["data"][ircLower(accountName)]["metadata"]:
				return True
			return False
		except KeyError:
			return None
	
	def getMetadataValue(self, accountName: str, key: str) -> Optional[str]:
		"""
		Returns the metadata value for the given metadata key on the given account.
		Returns None if the given account doesn't exist or the key isn't set.
		"""
		try:
			return self.accountData["data"][ircLower(accountName)]["metadata"][key]
		except KeyError:
			return None
	
	def checkAccountExistence(self, accountName: str) -> bool:
		"""
		Returns whether an account exists.
		"""
		if ircLower(accountName) in self.accountData["data"]:
			return True
		return False
	
	def updateLoggedInUsers(self, user: "IRCUser", key: str, oldValue: str, value: str, fromServer: "IRCServer" = None) -> None:
		if key != "account":
			return
		if oldValue is not None and oldValue in self.loggedInUsers:
			self.loggedInUsers[oldValue].discard(user)
		if value is not None:
			if value not in self.loggedInUsers:
				self.loggedInUsers[value] = WeakSet()
			self.loggedInUsers[value].add(user)
	
	def startBurst(self, server: "IRCServer") -> None:
		server.sendMessage("ACCOUNTBURSTINIT", accountFormatVersion, prefix=self.ircd.serverID)

@implementer(ICommand)
class AccountInfoCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 1:
			return None
		accountInfo = None
		try:
			accountInfo = deserializeAccount(params[0])
		except ValueError:
			return None
		return {
			"accountinfo": accountInfo
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		accountInfo = data["accountinfo"]
		self.module.registerAccountFromInfo(accountInfo, self.ircd.serverID < server.serverID, server)
		return True

@implementer(ICommand)
class CreateAccountCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		serializedAccountInfo = params[1]
		regTime = None
		try:
			regTime = datetime.utcfromtimestamp(float(params[0]))
		except (KeyError, ValueError):
			return None
		accountInfo = {}
		try:
			accountInfo = deserializeAccount(serializedAccountInfo)
		except ValueError:
			return None
		return {
			"regtime": regTime,
			"accountinfo": accountInfo
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		accountInfo = data["accountinfo"]
		accountName = accountInfo["username"]
		lowerAccountName = ircLower(accountName)
		
		if lowerAccountName in self.module.accountData["data"]:
			otherRegisterTime = self.module.accountData["data"][lowerAccountName]["registered"]
			thisRegisterTime = accountInfo["registered"]
			if otherRegisterTime < thisRegisterTime:
				self.ircd.log.debug("Ignoring request from server {server.serverID} to create account {name} due to timestamp mismatch (resolved with registration time)", name=accountName, server=server)
				return True
			if otherRegisterTime == thisRegisterTime:
				if len(self.module.accountData["data"][lowerAccountName]["nick"]) > len(accountInfo["nick"]):
					self.ircd.log.debug("Ignoring request from server {server.serverID} to create account {name} due to timestamp mismatch (resolved with nickname time)", name=accountName, server=server)
					return True
				if len(self.module.accountData["data"][lowerAccountName]["nick"]) == len(accountInfo["nick"]):
					# This is pretty likely the same account as what we have, so we'll let it through without deleting anything.
					return True
			self.module.deleteAccount(accountName, server)
		
		createResult = None
		try:
			createResult = self.module.createAccount(accountInfo["username"], accountInfo["password"], accountInfo["password-hash"], accountInfo["email"] if "email" in accountInfo else None, None, server)
		except KeyError as err:
			self.ircd.log.debug("Rejecting request from server {server.serverID} to create account {name} due to missing required information ({key})", name=accountName, server=server, key=err)
			return False
		if not createResult[0]:
			self.ircd.log.debug("Rejecting request from server {server.serverID} to create account {name} due to creation failing ({code})", name=accountName, server=server, code=createResult[1])
			return False
		self.ircd.log.debug("Created account {name} by request from server {server.serverID}", name=accountName, server=server)
		return True

@implementer(ICommand)
class DeleteAccountCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 3:
			return None
		deleteTime = None
		try:
			deleteTime = datetime.utcfromtimestamp(float(params[0]))
		except (TypeError, ValueError):
			return None
		
		registerTime = None
		try:
			registerTime = datetime.utcfromtimestamp(float(params[2]))
		except (TypeError, ValueError):
			return None
		return {
			"deletetime": deleteTime,
			"accountname": params[1],
			"registertime": registerTime
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		accountName = data["accountname"]
		registerTime = data["registertime"]
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.module.accountData["data"]:
			self.ircd.log.debug("Ignored request from server {server.serverID} to delete account {name} due to account not existing", name=accountName, server=server)
			return True
		if self.module.accountData["data"][lowerAccountName]["registered"] >= registerTime:
			self.module.deleteAccount(accountName, server)
		self.ircd.log.debug("Deleted account {name} by request from server {server.serverID}", name=accountName, server=server)
		return True

@implementer(ICommand)
class UpdateAccountNameCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 4:
			return None
		updateTime = None
		try:
			updateTime = datetime.utcfromtimestamp(float(params[0]))
		except (TypeError, ValueError):
			return None
		
		registerTime = None
		try:
			registerTime = datetime.utcfromtimestamp(float(params[2]))
		except (TypeError, ValueError):
			return None
		return {
			"updatetime": updateTime,
			"oldname": params[1],
			"registertime": registerTime,
			"newname": params[3]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		existingName = data["oldname"]
		lowerExistingName = ircLower(existingName)
		if lowerExistingName not in self.module.accountData["data"][lowerExistingName]:
			if lowerExistingName in self.module.accountData["deleted"]:
				self.ircd.log.debug("Ignoring request from server {server.serverID} to change account name for account {name} due to account being deleted", name=existingName, server=server)
				return True
			self.ircd.log.debug("Rejecting request from server {server.serverID} to change account name for account {name} due to account not existing", name=existingName, server=server)
			return False
		if self.module.accountData["data"][lowerExistingName]["registered"] < data["registertime"]:
			self.ircd.log.debug("Ignoring request from server {server.serverID} to change account name for account {name} due to timestamp mismatch", name=existingName, server=server)
			return True
		newName = data["newname"]
		nameChangeResult = self.module.changeAccountName(existingName, newName, server)
		if nameChangeResult[0]:
			self.ircd.log.debug("Changed account name from {oldName} to {newName} by request from server {server.serverID}", oldName=existingName, newName=newName, server=server)
			return True
		self.ircd.log.debug("Rejecting request from server {server.serverID} to change account name for account {name} due to error ({code})", name=existingName, server=server, code=nameChangeResult[1])
		return False

@implementer(ICommand)
class UpdateAccountPassCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 5:
			return None
		updateTime = None
		try:
			updateTime = datetime.utcfromtimestamp(float(params[0]))
		except (TypeError, ValueError):
			return None
		
		registerTime = None
		try:
			registerTime = datetime.utcfromtimestamp(float(params[2]))
		except (TypeError, ValueError):
			return None
		return {
			"updatetime": updateTime,
			"username": params[1],
			"registertime": registerTime,
			"password": params[3],
			"hashmethod": params[4]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.module.accountData["data"]:
			if lowerAccountName in self.module.accountData["deleted"]:
				self.ircd.log.debug("Ignoring request from server {server.serverID} to change password for account {name} due to account being deleted", name=accountName, server=server)
				return True
			self.ircd.log.debug("Rejecting request from server {server.serverID} to change password for account {name} due to account not existing", name=accountName, server=server)
			return False
		if self.module.accountData["data"][lowerAccountName]["registered"] < data["registertime"]:
			self.ircd.log.debug("Ignoring request from server {server.serverID} to change password for account {name} due to timestamp mismatch", name=accountName, server=server)
			return True
		changeResult = self.module.setPassword(accountName, data["password"], data["hashmethod"], server)
		if changeResult[0]:
			self.ircd.log.debug("Changed account password for {name} by request from server {server.serverID}", name=accountName, server=server)
			return True
		self.ircd.log.debug("Rejecting request from server {server.serverID} to change password for account {name} due to error ({code})", name=accountName, server=server, code=changeResult[1])
		return False

@implementer(ICommand)
class UpdateAccountEmailCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 4:
			return None
		updateTime = None
		try:
			updateTime = datetime.utcfromtimestamp(float(params[0]))
		except (TypeError, ValueError):
			return None
		
		registerTime = None
		try:
			registerTime = datetime.utcfromtimestamp(float(params[2]))
		except (TypeError, ValueError):
			return None
		return {
			"updatetime": updateTime,
			"username": params[1],
			"registertime": registerTime,
			"email": params[3]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.module.accountData["data"]:
			if lowerAccountName in self.module.accountData["deleted"]:
				self.ircd.log.debug("Ignoring request from server {server.serverID} to change email for account {name} due to account being deleted", name=accountName, server=server)
				return True
			self.ircd.log.debug("Rejecting request from server {server.serverID} to change email for account {name} due to account not existing", name=accountName, server=server)
			return False
		if self.module.accountData["data"][lowerAccountName]["registered"] < data["registertime"]:
			self.ircd.log.debug("Ignoring request from server {server.serverID} to change email for account {name} due to timestamp mismatch", name=accountName, server=server)
			return True
		changeResult = self.module.setEmail(accountName, data["email"], server)
		if changeResult[0]:
			self.ircd.log.debug("Changed account email for {name} by request from server {server.serverID}", name=accountName, server=server)
			return True
		self.ircd.log.debug("Rejecting request from server {server.serverID} to change email for account {name} due to error ({code})", name=accountName, server=server, code=changeResult[1])
		return False

@implementer(ICommand)
class AddAccountNickCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 4:
			return None
		updateTime = None
		try:
			updateTime = datetime.utcfromtimestamp(float(params[0]))
		except (TypeError, ValueError):
			return None
		
		registerTime = None
		try:
			registerTime = datetime.utcfromtimestamp(float(params[2]))
		except (TypeError, ValueError):
			return None
		return {
			"updatetime": updateTime,
			"username": params[1],
			"registertime": registerTime,
			"addnick": params[3]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		newNick = data["addnick"]
		if lowerAccountName not in self.module.accountData["data"]:
			if lowerAccountName in self.module.accountData["deleted"]:
				self.ircd.log.debug("Ignoring request from server {server.serverID} to add nickname {nick} to account {name} due to account being deleted", name=accountName, nick=newNick, server=server)
				return True
			self.ircd.log.debug("Rejecting request from server {server.serverID} to add nickname {nick} to account {name} due to account not existing", name=accountName, nick=newNick, server=server)
			return False
		if self.module.accountData["data"][lowerAccountName]["registered"] < data["registertime"]:
			self.ircd.log.debug("Ignoring request from server {server.serverID} to add nickname {nick} to account {name} due to timestamp mismatch", name=accountName, nick=newNick, server=server)
			return True
		addResult = self.module.addAltNick(accountName, newNick, server)
		if addResult[0]:
			self.ircd.log.debug("Added nickname {nick} to account {name} by request from server {server.serverID}", name=accountName, nick=newNick, server=server)
			return True
		self.ircd.log.debug("Rejecting request from server {server.serverID} to add nickname {nick} to account {name} due to error ({code})", name=accountName, nick=newNick, server=server, code=addResult[1])
		return False

@implementer(ICommand)
class RemoveAccountNickCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 4:
			return None
		removeTime = None
		try:
			removeTime = datetime.utcfromtimestamp(float(params[0]))
		except (TypeError, ValueError):
			return None
		
		registerTime = None
		try:
			registerTime = datetime.utcfromtimestamp(float(params[2]))
		except (TypeError, ValueError):
			return None
		return {
			"removetime": removeTime,
			"username": params[1],
			"registertime": registerTime,
			"removenick": params[3]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		removingNick = data["removenick"]
		if lowerAccountName not in self.module.accountData["data"]:
			if lowerAccountName in self.module.accountData["deleted"]:
				self.ircd.log.debug("Ignoring request from server {server.serverID} to remove nickname {nick} from account {name} due to account being deleted", name=accountName, nick=removingNick, server=server)
				return True
			self.ircd.log.debug("Rejecting request from server {server.serverID} to remove nickname {nick} from account {name} due to account not existing", name=accountName, nick=removingNick, server=server)
			return False
		if self.module.accountData["data"][lowerAccountName]["registered"] < data["registertime"]:
			self.ircd.log.debug("Ignoring request from server {server.serverID} to remove nickname {nick} from account {name} due to timestamp mismatch", name=accountName, nick=removingNick, server=server)
			return True
		removeResult = self.module.removeAltNick(accountName, removingNick, server)
		if removeResult[0]:
			self.ircd.log.debug("Removed nickname {nick} from account {name} by request from server {server.serverID}", name=accountName, nick=removingNick, server=server)
			return True
		if removeResult[1] == "NICKNOLINK":
			self.ircd.log.debug("Ignoring request from server {server.serverID} to remove nickname {nick} from account {name} due to nickname already being removed", name=accountName, nick=removingNick, server=server)
			return True
		self.ircd.log.debug("Rejecting request from server {server.serverID} to remove nickname {nick} from account {name} due to error ({code})", name=accountName, nick=removingNick, server=server, code=removeResult[1])
		return False

@implementer(ICommand)
class SetAccountMetadataCommand(Command):
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		"""
		if value is None:
			self.ircd.broadcastToServers(fromServer, "SETMETADATA", timestampStringFromTime(setTime), accountName, timestampStringFromTime(registerTime), key, prefix=self.ircd.serverID)
		else:
			self.ircd.broadcastToServers(fromServer, "SETMETADATA", timestampStringFromTime(setTime), accountName, timestampStringFromTime(registerTime), key, value, prefix=self.ircd.serverID)
		"""
		if len(params) != 4 and len(params) != 5:
			return None
		setTime = None
		try:
			setTime = datetime.utcfromtimestamp(float(params[0]))
		except (TypeError, ValueError):
			return None
		
		registerTime = None
		try:
			registerTime = datetime.utcfromtimestamp(float(params[2]))
		except (TypeError, ValueError):
			return None
		returnDict = {
			"settime": setTime,
			"username": params[1],
			"registertime": registerTime,
			"key": params[3]
		}
		if len(params) == 5:
			returnDict["value"] = params[4]
		return returnDict
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		settingKey = data["key"]
		settingValue = None
		if "value" in data:
			settingValue = data["value"]
		if lowerAccountName not in self.module.accountData["data"]:
			if lowerAccountName in self.module.accountData["deleted"]:
				self.ircd.log.debug("Ignoring request from server {server.serverID} to set metadata key {key} on account {name} due to account being deleted", name=accountName, key=settingKey, server=server)
				return True
			self.ircd.log.debug("Rejecting request from server {server.serverID} to set metadata key {key} on account {name} due to account not existing", name=accountName, key=settingKey, server=server)
			return False
		if self.module.accountData["data"][lowerAccountName]["registered"] < data["registertime"]:
			self.ircd.log.debug("Ignoring request from server {server.serverID} to set metadata key {key} on account {name} due to timestamp mismatch", name=accountName, key=settingKey, server=server)
			return True
		setResult = self.module.setMetadata(accountName, settingKey, settingValue, server)
		if setResult[0]:
			self.ircd.log.debug("Set metadata key {key} on account {name} by request from server {server.serverID}", name=accountName, key=settingKey, server=server)
			return True
		self.ircd.log.debug("Rejecting request from server {server.serverID} to set metadata key {key} on account {name} due to error ({code})", name=accountName, key=settingKey, server=server, code=setResult[1])
		return False

@implementer(ICommand)
class AccountBurstInitCommand(Command):
	burstQueuePriority = 1
	
	def __init__(self, module: Accounts):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 1:
			return None
		return {
			"version": params[0]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if data["version"] != accountFormatVersion:
			return False
		for account in self.module.accountData["data"].values():
			server.sendMessage("ACCOUNTINFO", serializeAccount(account), prefix=self.ircd.serverID)
		for accountName, deleteData in self.module.accountData["deleted"].values():
			server.sendMessage("DELETEACCOUNT", timestampStringFromTime(deleteData["deleted"]), accountName, timestampStringFromTime(deleteData["created"]))
		self.ircd.runActionStandard("afteraccountburst", server)
		return True

accountController = Accounts()

def serializeAccount(accountInfo: Dict[str, Any]) -> str:
	"""
	Serializes an account dict.
	"""
	builtResultString = []
	for key, value in accountInfo.items():
		builtResultString.append("{}:{};".format(_escapeSerializedString(key), _serializeValue(value)))
	return "".join(builtResultString)[:-1]

def _serializeValue(value: Any) -> str:
	if value is None:
		return "N"
	if value is True:
		return "T1"
	if value is False:
		return "T0"
	try:
		subDictSerialized = serializeAccount(value)
		return "{{{}".format(_escapeSerializedString(subDictSerialized))
	except (TypeError, AttributeError):
		pass
	try:
		value.lower() # Discard the result; this tests for string
		return "\"{}".format(_escapeSerializedString(value))
	except AttributeError:
		pass
	try:
		listResults = []
		for listValue in value:
			listResults.append(",{}".format(_escapeSerializedString(_serializeValue(listValue))))
		return "[{}".format("".join(listResults)[1:])
	except TypeError:
		pass
	if isinstance(value, datetime):
		return "D{}".format(timestamp(value))
	if isinstance(value, float):
		return ".{}".format(value)
	return "#{}".format(value)

def _escapeSerializedString(value: str) -> str:
	value = value.replace("\\", "\\\\")
	value = value.replace(";", "\\|")
	value = value.replace(":", "\\=")
	value = value.replace(",", "\\.")
	value = value.replace("\r", "\\r")
	value = value.replace("\n", "\\n")
	value = value.replace(" ", "\\s")
	return value

def _unescapeSerializedString(value: str) -> str:
	resultValueChars = []
	escaping = False
	for char in value:
		if escaping:
			if char == "\\":
				resultValueChars.append("\\")
			elif char == "|":
				resultValueChars.append(";")
			elif char == "=":
				resultValueChars.append(":")
			elif char == ".":
				resultValueChars.append(",")
			elif char == "r":
				resultValueChars.append("\r")
			elif char == "n":
				resultValueChars.append("\n")
			elif char == "s":
				resultValueChars.append(" ")
			else:
				raise ValueError("\"{}\" is not a valid escaped serialized string.".format(value))
			escaping = False
			continue
		if char == "\\":
			escaping = True
			continue
		resultValueChars.append(char)
	if escaping:
		raise ValueError("\"{}\" is not a valid escaped serialized string.".format(value))
	return "".join(resultValueChars)

def deserializeAccount(accountInfoString: str) -> Dict[str, Any]:
	"""
	Deserializes a string back into a dict.
	Raises an error if the string is invalid.
	"""
	if not accountInfoString:
		return {}
	
	deserializedData = {}
	
	for accountInfoPart in accountInfoString.split(";"):
		key, value = _deserializeStringPart(accountInfoPart)
		deserializedData[key] = value
	return deserializedData
	
def _deserializeStringPart(stringPart: str) -> Tuple[str, Any]:
	if ":" not in stringPart:
		raise ValueError("\"{}\" is not a valid serialized substring.".format(stringPart))
	key, valueInfo = stringPart.split(":", 1)
	return _unescapeSerializedString(key), _deserializeStringValue(valueInfo)

def _deserializeStringValue(valueInfo: str) -> Any:
	valueType = valueInfo[0]
	serializedValue = valueInfo[1:]
	if valueType == "N":
		return None
	if valueType == "T":
		try:
			return bool(int(serializedValue))
		except ValueError:
			raise ValueError("Serialized substring \"{}\" has a boolean type but a non-boolean value.".format(valueInfo))
	if valueType == "{":
		return deserializeAccount(_unescapeSerializedString(serializedValue))
	if valueType == "[":
		valueParts = []
		for valuePart in serializedValue.split(","):
			valueParts.append(_deserializeStringValue(_unescapeSerializedString(valuePart)))
		return valueParts
	if valueType == "\"":
		return _unescapeSerializedString(serializedValue)
	if valueType == "D":
		try:
			return datetime.utcfromtimestamp(float(serializedValue))
		except ValueError:
			raise ValueError("Serialized substring \"{}\" has a date type but is not a valid timestamp.".format(valueInfo))
	if valueType == ".":
		try:
			return float(serializedValue)
		except ValueError:
			raise ValueError("Serialized substring \"{}\" has a float type but a non-float value.".format(valueInfo))
	if valueType == "#":
		try:
			return int(serializedValue)
		except ValueError:
			raise ValueError("Serialized substring \"{}\" has an int type but a non-int value.".format(valueInfo))
	raise ValueError("Serialized substring \"{}\" has an invalid type.".format(valueInfo))