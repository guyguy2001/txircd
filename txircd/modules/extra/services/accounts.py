from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import CaseInsensitiveDictionary, ircLower, isValidNick, now, timestamp, timestampStringFromTime, timestampStringFromTimestamp
from zope.interface import implements
from validate_email import validate_email as validateEmail
from datetime import datetime, timedelta
from weakref import WeakSet

accountFormatVersion = "0"

class Accounts(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "Accounts"
	
	def actions(self):
		return [ ("createnewaccount", 1, self.createAccount),
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
			("accountlistallnames", 1, self.allAccountNames),
			("accountlistnicks", 1, self.accountNicks),
			("accountgetemail", 1, self.getEmail),
			("accountgetregtime", 1, self.getRegTime),
			("accountgetlastlogin", 1, self.getLastLogin),
			("accountgetusers", 1, self.getAccountUsers),
			("checkaccountexists", 1, self.checkAccountExistence),
			("usermetadataupdate", 10, self.updateLastLoginTime),
			("usermetadataupdate", 1, self.updateLoggedInUsers),
			("burst", 5, self.startBurst) ]
	
	def serverCommands(self):
		return [ ("CREATEACCOUNT", 1, CreateAccountCommand(self)),
			("DELETEACCOUNT", 1, DeleteAccountCommand(self)),
			("UPDATEACCOUNTNAME", 1, UpdateAccountNameCommand(self)),
			("UPDATEACCOUNTPASS", 1, UpdateAccountPassCommand(self)),
			("UPDATEACCOUNTEMAIL", 1, UpdateAccountEmailCommand(self)),
			("ADDACCOUNTNICK", 1, AddAccountNickCommand(self)),
			("REMOVEACCOUNTNICK", 1, RemoveAccountNickCommand(self)),
			("ACCOUNTBURSTINIT", 1, AccountBurstInitCommand(self)) ]
	
	def load(self):
		if "services" not in self.ircd.storage:
			self.ircd.storage["services"] = {}
			self.ircd.storage["services"]["journal"] = []
			self.ircd.storage["services"]["serverupdates"] = {}
		if "accounts" not in self.ircd.storage["services"]:
			self.ircd.storage["services"]["accounts"] = {}
			self.ircd.storage["services"]["accounts"]["data"] = {}
			self.ircd.storage["services"]["accounts"]["index"] = {}
			self.ircd.storage["services"]["accounts"]["deleted"] = {}
		self.servicesData = self.ircd.storage["services"]
		self.accountData = self.servicesData["accounts"]
		self.loggedInUsers = CaseInsensitiveDictionary()
	
	def verifyConfig(self, config):
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
	
	def createAccount(self, username, password, passwordHashedMethod, email, user, extraInfo, fromServer = None):
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
		if not passwordHashedMethod is None and len(password) < self.ircd.config["account_password_minimum_length"]:
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
		
		if not isValidNick(username) or len(username) > self.ircd.config.get("nick_length", 32):
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
		newAccountInfo = extraInfo.copy() if extraInfo else {}
		newAccountInfo["username"] = username
		newAccountInfo["password"] = hashedPassword
		newAccountInfo["password-hash"] = passwordHashMethod
		newAccountInfo["nick"] = [(username, timestamp(registrationTime))]
		if email:
			newAccountInfo["email"] = email
		if "registered" not in newAccountInfo:
			newAccountInfo["registered"] = timestamp(registrationTime)
		newAccountInfo["settings"] = {}
		
		self.accountData["data"][lowerUsername] = newAccountInfo
		if lowerUsername in self.accountData["deleted"]:
			del self.accountData["deleted"][lowerUsername]
		
		self.ircd.runActionStandard("accountsetupindices", username)
		
		serializedAccountInfo = serializeAccount(newAccountInfo)
		self.servicesData["journal"].append((registrationTime, "CREATEACCOUNT", serializedAccountInfo))
		self.ircd.broadcastToServers(fromServer, "CREATEACCOUNT", timestampStringFromTime(registrationTime), serializedAccountInfo, prefix=self.ircd.serverID)
		if user and user.uuid[:3] == self.ircd.serverID:
			user.setMetadata("account", username, "internal", False)
		
		self._serverUpdateTime(registrationTime)
		self.ircd.runActionStandard("accountcreated", username)
		return True, None, None
	
	def indexAccount(self, accountName):
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
	
	def unindexAccount(self, accountName):
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
	
	def authenticateUser(self, user, username, password, completeLogin = True):
		"""
		Authenticates a user for an account.
		Accepts a username (or, for other functions implementing this action, another unique piece of account information)
		and password, and it checks whether the user is allowed to be signed into that account.
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
		if loginExtraCheckResult and loginExtraCheckResult[0] is False:
			return loginExtraCheckResult
		
		if completeLogin:
			username = self.accountData["data"][lowerUsername]["username"]
			user.setMetadata("account", username, "internal", False)
		return True, None, None
	
	def updateLastLoginTime(self, user, key, oldValue, value, visibility, setByUser, fromServer = None):
		if key != "account":
			return
		if value is None:
			return # This doesn't apply for users logging out
		lowerAccountName = ircLower(value)
		if lowerAccountName not in self.accountData["data"]:
			return
		self.accountData["data"][lowerAccountName]["lastlogin"] = timestamp(now())
	
	def logUserOut(self, user):
		"""
		Logs a user out of the account into which they are logged.
		"""
		user.setMetadata("account", None, "internal", False)
		return True
	
	def deleteAccount(self, username, fromServer = None):
		"""
		Deletes an account.
		"""
		lowerUsername = ircLower(username)
		if lowerUsername not in self.accountData["data"]:
			return False, "NOEXIST", "Account not registered."
		self.ircd.runActionStandard("accountremoveindices", lowerUsername)
		username = self.accountData["data"][lowerUsername]["username"]
		for user in self.ircd.users.itervalues():
			if user.metadataValue("account") == username:
				self.ircd.runActionStandard("accountlogout", user)
		createTimestamp = self.accountData["data"][lowerUsername]["registered"]
		
		deleteTime = now()
		del self.accountData["data"][lowerUsername]
		self.accountData["deleted"][lowerUsername] = timestamp(deleteTime)
		self.servicesData["journal"].append((deleteTime, "DELETEACCOUNT", username))
		self.ircd.broadcastToServers(fromServer, "DELETEACCOUNT", timestampStringFromTime(deleteTime), username, timestampStringFromTimestamp(createTimestamp), prefix=self.ircd.serverID)
		for user in self.ircd.users.itervalues():
			if user.metadataKeyExists("account") and ircLower(user.metadataValue("account")) == lowerUsername:
				user.setMetadata("account", None, "internal", False)
		self._serverUpdateTime(deleteTime)
		return True, None, None
	
	def changeAccountName(self, oldAccountName, newAccountName, fromServer = None):
		"""
		Changes the account name for an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		lowerOldAccountName = ircLower(oldAccountName)
		
		self.cleanOldDeleted()
		if lowerOldAccountName not in self.accountData["data"]:
			return False, "BADACCOUNT", "The account does not exist."
		
		if not isValidNick(newAccountName) or len(newAccountName) > self.ircd.config.get("nick_length", 32):
			return False, "BADUSER", "The username is not a valid nickname"
		
		lowerNewAccountName = ircLower(newAccountName)
		for nickname, registrationTime in self.accountData["data"][lowerOldAccountName]["nick"]:
			if lowerNewAccountName == ircLower(nickname):
				break
		else:
			return False, "NONICKLINK", "The new account name isn't associated with the account. The new account name should be grouped with the existing account as an alternate nickname."
		accountInfo = self.accountData["data"][lowerOldAccountName]
		del self.accountData["data"][lowerOldAccountName]
		accountInfo["username"] = newAccountName
		registerTimestamp = accountInfo["registered"]
		updateTime = now()
		if "oldnames" not in accountInfo:
			accountInfo["oldnames"] = []
		accountInfo["oldNames"].append((oldAccountName, timestamp(updateTime)))
		self.accountData["data"][lowerNewAccountName] = accountInfo
		self.servicesData["journal"].append((updateTime, "UPDATEACCOUNTNAME", oldAccountName, newAccountName))
		self.ircd.broadcastToServers(fromServer, "UPDATEACCOUNTNAME", timestampStringFromTime(updateTime), oldAccountName, timestampStringFromTimestamp(registerTimestamp), newAccountName, prefix=self.ircd.serverID)
		self._serverUpdateTime(updateTime)
		if not fromServer:
			for user in self.ircd.users.itervalues():
				if user.metadataKeyExists("account") and ircLower(user.metadataValue("account")) == lowerOldAccountName:
					user.setMetadata("account", newAccountName, "internal", False)
		return True, None, None
	
	def setPassword(self, accountName, password, hashMethod, fromServer = None):
		"""
		Set the password for an account.
		For plain passwords, the hashMethod is None.
		If it's not, the password must be hashed with that hash method, and the hash method module must be loaded.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		self.cleanOldDeleted()
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
		registerTimestamp = self.accountData["data"][lowerAccountName]["registered"]
		self.servicesData["journal"].append((updateTime, "UPDATEACCOUNTPASS", accountName, hashedPassword, hashMethod))
		self.ircd.broadcastToServers(fromServer, "UPDATEACCOUNTPASS", timestampStringFromTime(updateTime), accountName, timestampStringFromTimestamp(registerTimestamp), hashedPassword, hashMethod, prefix=self.ircd.serverID)
		self._serverUpdateTime(updateTime)
		return True, None, None
	
	def setEmail(self, accountName, email, fromServer = None):
		"""
		Sets the email address for an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		self.cleanOldDeleted()
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
		registerTimestamp = self.accountData["data"][lowerAccountName]["registered"]
		self.servicesData["journal"].append((updateTime, "UPDATEACCOUNTEMAIL", accountName, email))
		self.ircd.broadcastToServers(fromServer, "UPDATEACCOUNTEMAIL", timestampStringFromTime(updateTime), accountName, timestampStringFromTimestamp(registerTimestamp), email, prefix=self.ircd.serverID)
		self._serverUpdateTime(updateTime)
		self.ircd.runActionStandard("accountsetupindices", accountName)
		return True, None, None
	
	def addAltNick(self, accountName, newNick, fromServer = None):
		"""
		Adds a nickname to an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		self.cleanOldDeleted()
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
		self.accountData["data"][lowerAccountName]["nick"].append((newNick, timestamp(now())))
		addTime = now()
		registerTimestamp = self.accountData["data"][lowerAccountName]["registered"]
		self.servicesData["journal"].append((addTime, "ADDACCOUNTNICK", accountName, newNick))
		self.ircd.broadcastToServers(fromServer, "ADDACCOUNTNICK", timestampStringFromTime(addTime), accountName, timestampStringFromTimestamp(registerTimestamp), newNick, prefix=self.ircd.serverID)
		self._serverUpdateTime(addTime)
		self.ircd.runActionStandard("accountsetupindices", accountName)
		return True, None, None
	
	def removeAltNick(self, accountName, oldNick, fromServer = None):
		"""
		Removes a nickname from an account.
		Returns (True, None, None) if successful or (False, ERRCODE, error message) if not.
		"""
		self.cleanOldDeleted()
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
		registerTimestamp = self.accountData["data"][lowerAccountName]["registered"]
		self.servicesData["journal"].append((removeTime, "REMOVEACCOUNTNICK", accountName, oldNick))
		self.ircd.broadcastToServers(fromServer, "REMOVEACCOUNTNICK", timestampStringFromTime(removeTime), accountName, timestampStringFromTimestamp(registerTimestamp), oldNick, prefix=self.ircd.serverID)
		self._serverUpdateTime(removeTime)
		self.ircd.runActionStandard("accountsetupindices", accountName)
		return True, None, None
	
	def allAccountNames(self):
		"""
		Returns a list of all registered account names.
		"""
		return self.accountData["data"].keys()
	
	def accountNicks(self, accountName):
		"""
		Returns all nicknames associated with the account.
		If the account doesn't exist, returns None.
		"""
		try:
			return self.accountData["data"][ircLower(accountName)]["nick"]
		except KeyError:
			return None
	
	def getEmail(self, accountName):
		"""
		Returns the email address associated with an account, if populated.
		"""
		try:
			return self.accountData["data"][ircLower(accountName)]["email"]
		except KeyError:
			return None
	
	def getRegTime(self, accountName):
		"""
		Returns the registration time for a user.
		"""
		try:
			return datetime.utcfromtimestamp(self.accountData["data"][ircLower(accountName)]["registration"])
		except KeyError:
			return None
	
	def getLastLogin(self, accountName):
		"""
		Returns the last login time for a user.
		"""
		try:
			return datetime.utcfromtimestamp(self.accountData["data"][ircLower(accountName)]["lastlogin"])
		except KeyError:
			return None
	
	def getAccountUsers(self, accountName):
		"""
		Returns a list of currently logged-in users for an account.
		"""
		if accountName in self.loggedInUsers:
			return list(self.loggedInUsers[accountName])
		return None
	
	def checkAccountExistence(self, accountName):
		"""
		Returns whether an account exists.
		"""
		if ircLower(accountName) in self.accountData["data"]:
			return True
		return False
	
	def updateLoggedInUsers(self, user, key, oldValue, value, visibility, setByUser, fromServer = None):
		if key != "account":
			return
		if oldValue is not None and oldValue in self.loggedInUsers:
			self.loggedInUsers[oldValue].discard(user)
		if value is not None:
			if value not in self.loggedInUsers:
				self.loggedInUsers[value] = WeakSet()
			self.loggedInUsers[value].add(user)
	
	def cleanOldDeleted(self):
		"""
		Cleans up old deleted account info.
		"""
		oneHour = timedelta(hours=1)
		expireOlderThan = now() - oneHour
		removeAccounts = []
		for account, deleteTime in self.accountData["deleted"].iteritems():
			if deleteTime < expireOlderThan:
				removeAccounts.append(account)
		for account in removeAccounts:
			del self.accountData["deleted"][account]
	
	def _serverUpdateTime(self, time):
		syncTimestamp = timestamp(time)
		for server in self.ircd.servers.itervalues():
			self.servicesData["serverupdates"][server.serverID] = syncTimestamp
	
	def startBurst(self, server):
		lastSyncTimestamp = 0
		if server.serverID in self.servicesData["serverupdates"]:
			lastSyncTimestamp = self.servicesData["serverupdates"][server.serverID]
		server.sendMessage("ACCOUNTBURSTINIT", accountFormatVersion, timestampStringFromTimestamp(lastSyncTimestamp), prefix=self.ircd.serverID)

class CreateAccountCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
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
	
	def execute(self, server, data):
		accountInfo = data["accountinfo"]
		accountName = accountInfo["username"]
		lowerAccountName = ircLower(accountName)
		
		if lowerAccountName in self.module.accountData["data"]:
			otherRegisterTime = datetime.utcfromtimestamp(self.module.accountData["data"][lowerAccountName]["registered"])
			thisRegisterTime = datetime.utcfromtimestamp(accountInfo["registered"])
			if otherRegisterTime < thisRegisterTime:
				return True
			if otherRegisterTime == thisRegisterTime:
				if len(self.module.accountData["data"][lowerAccountName]["nick"]) > len(accountInfo["nick"]):
					return True
				if len(self.module.accountData["data"][lowerAccountName]["nick"]) == len(accountInfo["nick"]):
					# We're getting really, really desperate to resolve this conflict now
					# Random will be different between servers, so we use server ID here
					if server.serverID > self.ircd.serverID:
						return True
			self.module.deleteAccount(accountName, server)
		
		try:
			if not self.module.createAccount(accountInfo["username"], accountInfo["password"], accountInfo["password-hash"], accountInfo["email"] if "email" in accountInfo else None, None, accountInfo, server)[0]:
				return False
		except KeyError:
			return False
		return True

class DeleteAccountCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
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
	
	def execute(self, server, data):
		accountName = data["accountname"]
		registerTime = data["registertime"]
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.module.accountData["data"]:
			return True
		if datetime.utcfromtimestamp(self.module.accountData["data"][lowerAccountName]["registered"]) >= registerTime:
			self.module.deleteAccount(accountName, server)
		return True

class UpdateAccountNameCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
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
	
	def execute(self, server, data):
		existingName = data["oldname"]
		lowerExistingName = ircLower(existingName)
		if lowerExistingName not in self.module.accountData["data"][lowerExistingName]:
			self.module.cleanOldDeleted()
			if lowerExistingName in self.module.accountData["deleted"]:
				return True
			return False
		if datetime.utcfromtimestamp(self.module.accountData["data"][lowerExistingName]["registered"]) < data["registertime"]:
			return True
		if self.module.changeAccountName(existingName, data["newname"], server)[0]:
			return True
		return False

class UpdateAccountPassCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
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
	
	def execute(self, server, data):
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.module.accountData["data"]:
			self.module.cleanOldDeleted()
			if lowerAccountName in self.module.accountData["deleted"]:
				return True
			return False
		if datetime.utcfromtimestamp(self.module.accountData["data"][lowerAccountName]["registered"]) < data["registertime"]:
			return True
		if self.module.setPassword(accountName, data["password"], data["hashmethod"], server)[0]:
			return True
		return False

class UpdateAccountEmailCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
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
	
	def execute(self, server, data):
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.module.accountData["data"]:
			self.module.cleanOldDeleted()
			if lowerAccountName in self.module.accountData["deleted"]:
				return True
			return False
		if datetime.utcfromtimestamp(self.module.accountData["data"][lowerAccountName]["registered"]) < data["registertime"]:
			return True
		if self.module.setEmail(accountName, data["email"], server)[0]:
			return True
		return False

class AddAccountNickCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
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
	
	def execute(self, server, data):
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.module.accountData["data"]:
			self.module.cleanOldDeleted()
			if lowerAccountName in self.module.accountData["deleted"]:
				return True
			return False
		if datetime.utcfromtimestamp(self.module.accountData["data"][lowerAccountName]["registered"]) < data["registertime"]:
			return True
		if self.module.addAltNick(accountName, data["addnick"], server)[0]:
			return True
		return False

class RemoveAccountNickCommand(Command):
	implements(ICommand)
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
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
	
	def execute(self, server, data):
		accountName = data["username"]
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.module.accountData["data"]:
			self.module.cleanOldDeleted()
			if lowerAccountName in self.module.accountData["deleted"]:
				return True
			return False
		if datetime.utcfromtimestamp(self.module.accountData["data"][lowerAccountName]["registered"]) < data["registertime"]:
			return True
		if self.module.removeAltNick(accountName, data["removenick"], server)[0]:
			return True
		return False

class AccountBurstInitCommand(Command):
	implements(ICommand)
	
	burstQueuePriority = 1
	
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server, params, prefix, tags):
		if len(params) != 2:
			return None
		lastSyncTime = None
		try:
			lastSyncTime = datetime.utcfromtimestamp(float(params[1]))
		except (TypeError, ValueError):
			return None
		return {
			"version": params[0],
			"synctime": lastSyncTime
		}
	
	def execute(self, server, data):
		if data["version"] != accountFormatVersion:
			return False
		lastSyncTime = data["synctime"]
		for journalData in self.module.servicesData["journal"]:
			if datetime.utcfromtimestamp(journalData[0]) >= lastSyncTime:
				server.sendMessage(journalData[1], journalData[0], *journalData[2])
		self.module.servicesData["serverupdates"][server.serverID] = timestamp(now())
		return True

accountController = Accounts()

def serializeAccount(accountInfo):
	"""
	Serializes an account dict.
	"""
	builtResultString = []
	for key, value in accountInfo.iteritems():
		builtResultString.append("{}:{};".format(_escapeSerializedString(key), _serializeValue(value)))
	return "".join(builtResultString)[:-1]

def _serializeValue(value):
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
	if isinstance(value, float):
		return ".{}".format(value)
	return "#{}".format(value)

def _escapeSerializedString(value):
	value = value.replace("\\", "\\\\")
	value = value.replace(";", "\\|")
	value = value.replace(":", "\\=")
	value = value.replace(",", "\\.")
	value = value.replace("\r", "\\r")
	value = value.replace("\n", "\\n")
	value = value.replace(" ", "\\s")
	return value

def _unescapeSerializedString(value):
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

def deserializeAccount(accountInfoString):
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
	
def _deserializeStringPart(stringPart):
	if ":" not in stringPart:
		raise ValueError("\"{}\" is not a valid serialized substring.".format(stringPart))
	key, valueInfo = stringPart.split(":", 1)
	return _unescapeSerializedString(key), _deserializeStringValue(valueInfo)

def _deserializeStringValue(valueInfo):
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