from twisted.internet.defer import Deferred
from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ircLower
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from validate_email import validate_email as validateEmail

@implementer(IPlugin, IModuleData)
class DBDonorAccount(ModuleData):
	name = "DBDonorAccount"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("updatestoragereferences", 1, self.setStorageReferences),
			("accountsetupindices", 90, self.indexDonorID),
			("accountremoveindices", 90, self.unindexDonorID),
			("accountsetmetadataextracheck", 10, self.checkSetDonorID),
			("accountauthenticate", 2, self.logUserIn) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("DONORACCTIDREQ", 1, DonorAccountIDRequest(self)),
			("DONORACCOTIDRESP", 1, DonorAccountIDResponse(self)) ]
	
	def load(self) -> None:
		self.authCheckID = 0
		self.pendingAuthRequests = {}
		self.setStorageReferences()
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "donor_linked_server" in config and config["donor_linked_server"] is not None:
			if not isinstance(config["donor_linked_server"], str):
				raise ConfigValidationError("donor_linked_server", "must be a string (server name) or null")
		else:
			config["donor_linked_server"] = None
	
	def setStorageReferences(self) -> None:
		self.servicesData = self.ircd.storage["services"]
		self.accountData = self.servicesData["accounts"]
	
	def indexDonorID(self, accountName: str) -> None:
		if "donorid" not in self.accountData["index"]:
			self.accountData["index"]["donorid"] = {}
		lowerAccountName = ircLower(accountName)
		if lowerAccountName not in self.accountData["data"]:
			return
		if self.ircd.runActionUntilValue("accountgetmetadatakeyexists", accountName, "donorid"):
			donorID = self.ircd.runActionUntilValue("accountgetmetadatavalue", accountName, "donorid")
			self.accountData["index"]["donorid"][donorID] = lowerAccountName
	
	def unindexDonorID(self, accountName: str) -> None:
		if self.ircd.runActionUntilValue("accountgetmetadatakeyexists", accountName, "donorid"):
			donorID = self.ircd.runActionUntilValue("accountgetmetadatavalue", accountName, "donorid")
			del self.accountData["index"]["donorid"][donorID]
	
	def checkSetDonorID(self, accountName: str, key: str, value: Optional[str]) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, Deferred, None], None]:
		if key != "donorid":
			return None
		if value is None:
			return None
		lowerAccountName = ircLower(accountName)
		if value in self.accountData["index"]["donorid"] and self.accountData["index"]["donorid"][value] != lowerAccountName:
			return False, "DUPLICATEDONORID", "The same donor ID is being used for more than one account. That's not right."
		return True, None, None
	
	def logUserIn(self, user: "IRCUser", username: str, password: str, completeLogin: bool = True) -> Union[Tuple[bool, Optional[str], Optional[str]], Tuple[None, Deferred, None], None]:
		if "donor-login-inprogress" in user.cache:
			return False, "INPROGRESS", "Your previous login attempt is still being processed."
		if not validateEmail(username):
			return None # Fall back on the standard account system (logging in with a username)
		if "compare-pbkdf2" not in self.ircd.functionCache:
			return False, "NOPASS", "Cannot verify passwords against database. Please try again later."
		if self.ircd.config["donor_linked_server"] is None:
			resultDeferred = self.startDatabaseRequest(user, username, password)
			if resultDeferred is None:
				return False, "NODATA", "Cannot retrieve information from database. Please try again later."
			user.cache["donor-login-inprogress"] = resultDeferred
			return None, resultDeferred, None
		
		serverName = self.ircd.config["donor_linked_server"]
		if serverName not in self.ircd.serverNames:
			return False, "NODATA", "Cannot retrieve information from database. Please try again later."
		server = self.ircd.serverNames[serverName]
		self.authCheckID += 1
		server.sendMessage("DONORACCTIDREQ", server.serverID, username, password, prefix=self.ircd.serverID, tags={"reqid": "{}".format(self.authCheckID)})
		resultDeferred = Deferred()
		self.pendingAuthRequests[self.authCheckID] = resultDeferred
		user.cache["donor-login-inprogress"] = resultDeferred
		return None, resultDeferred, None
	
	def startDatabaseRequest(self, user: "IRCUser", email: str, password: str) -> Optional[Deferred]:
		email = ircLower(email)
		resultDeferred = self.ircd.runActionUntilValue("donordatabasequery", "SELECT id, password FROM donors WHERE email = %s", email)
		if resultDeferred is None:
			return None
		resultDeferred.addCallback(self.completeDatabaseCheck, user, email, password)
		return resultDeferred
	
	def completeDatabaseCheck(self, result: List[Tuple[int, str]], user: "IRCUser", email: str, password: str) -> None:
		"""
		Completes the database check from startDatabaseRequest. Expects the results as a list of (donor_id, password).
		The return value of this is passed on to later callbacks of the Deferred.
		"""
		if "donor-login-inprogress" in user.cache:
			del user.cache["donor-login-inprogress"]
		if user.uuid not in self.ircd.users:
			return False, "NOCONNECTION", "You are no longer connected."
		if "compare-pbkdf2" not in self.ircd.functionCache:
			return False, "NOPASS", "Cannot verify passwords against database. Please try again later."
		if not result: # Email address not found in database
			return False, "WRONG", "Login credentials were incorrect."
		if len(result) > 1:
			self.ircd.log.info("Found duplicate email address {email} in database", email=email)
		donorID = str(result[0][0])
		hashedPass = result[0][1]
		if self.ircd.functionCache["compare-pbkdf2"](password, hashedPass):
			if donorID in self.accountData["index"]["donorid"]:
				lowerAccountName = self.accountData["index"]["donorid"][donorID]
				self.ircd.runActionUntilValue("accountchangepass", lowerAccountName, hashedPass, "pbkdf2")
			else:
				registerResult = self.ircd.runActionUntilValue("createnewaccount", user.nick, hashedPass, "pbkdf2", email, user, users=[user])
				if not registerResult:
					return False, "NOACCOUNT", "Accounts are not set up on this server."
				if not registerResult[0]:
					return registerResult
				metadataResult = self.ircd.runActionUntilValue("accountsetmetadata", user.nick, "donorid", donorID, users=[user])
				if not metadataResult:
					self.ircd.runActionUntilValue("deleteaccount", user.nick)
					return False, "NOACCOUNT", "Accounts are not set up properly on this server."
				if not metadataResult[0]:
					self.ircd.runActionUntilValue("deleteaccount", user.nick)
					return metadataResult
				lowerAccountName = ircLower(user.nick)
			accountName = self.accountData["data"][lowerAccountName]["username"]
			user.setMetadata("account", accountName)
			return True, None, None
		return False, "WRONG", "Login credentials were incorrect."
	
	def sendRequestResponse(self, result: Tuple[Optional[bool], Union[str, Deferred, None], Union[str, None]], user: "IRCUser", requestID: str) -> None:
		if user.uuid[:3] == self.ircd.serverID:
			return
		userServer = self.ircd.servers[user.uuid[:3]]
		if result[0]:
			accountName = user.metadataValue("account")
			donorID = self.ircd.runActionUntilValue("accountgetmetadatavalue", accountName, "donorid")
			userServer.sendMessage("DONORACCTIDRESP", user.uuid, donorID, prefix=self.ircd.serverID, tags={"reqid": requestID})
			return
		userServer.sendMessage("DONORACCTIDRESP", user.uuid, result[1], result[2], prefix=self.ircd.serverID, tags={"reqid": requestID})

@implementer(ICommand)
class DonorAccountIDRequest(Command):
	def __init__(self, module: DBDonorAccount):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if "reqid" not in tags:
			return None
		if prefix not in self.ircd.users:
			return None
		if not params or len(params) != 3:
			return None
		if params[0] not in self.ircd.servers and params[0] != self.ircd.serverID:
			return None
		return {
			"requestid": tags["reqid"],
			"fromuser": self.ircd.users[prefix],
			"toserverid": params[0],
			"email": params[1],
			"password": params[2]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		fromUser = data["fromuser"]
		fromServer = self.ircd.servers[fromUser.uuid[:3]]
		toServerID = data["toserverid"]
		if toServerID == self.ircd.serverID:
			resultDeferred = self.module.startDatabaseRequest(fromUser, data["email"], data["password"])
			if resultDeferred is None:
				server.send("DONORACCTIDRESP", fromUser.uuid, "NODATA", "Cannot retrieve information from database. Please try again later.", prefix=self.ircd.serverID, tags={"reqid": data["requestid"]})
				return True
			resultDeferred.addCallback(self.module.sendRequestResponse, fromUser, data["requestid"])
			return True
		toServer = self.ircd.servers[toServerID]
		toServer.sendMessage("DONORACCTIDREQ", toServerID, data["email"], data["password"], prefix=fromServer.serverID, tags={"reqid": data["requestid"]})
		return True

@implementer(ICommand)
class DonorAccountIDResponse(Command):
	def __init__(self, module):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2 and len(params) != 3:
			return None
		if "reqid" not in tags:
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True,
					"requestid": tags["reqid"]
				}
			return None
		if len(params) == 2:
			try:
				return {
					"user": self.ircd.users[params[0]],
					"donorid": int(1),
					"requestid": tags["reqid"]
				}
			except ValueError:
				return None
		return {
			"user": self.ircd.users[params[0]],
			"errorcode": params[1],
			"errordesc": params[2],
			"requestid": tags["reqid"]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		requestID = data["requestid"]
		user = data["user"]
		if user.uuid[:3] != self.ircd.serverID:
			toServer = self.ircd.servers[user.uuid[:3]]
			if "donorid" in data:
				toServer.sendMessage("DONORACCTIDRESP", user.uuid, data["donorid"], prefix=self.ircd.serverID, tags={"reqid": requestID})
			else:
				toServer.sendMessage("DONORACCTIDRESP", user.uuid, data["errorcode"], data["errordesc"], prefix=self.ircd.serverID, tags={"reqid": requestID})
			return True
		
		if "lostuser" in data:
			if requestID in self.module.pendingAuthRequests:
				del self.module.pendingAuthRequests[requestID]
			return True
		requestDeferred = self.module.pendingAuthRequests[requestID]
		del self.module.pendingAuthRequests[requestID]
		if "donorid" in data:
			requestDeferred.callback((True, None, None))
		else:
			requestDeferred.callback((False, data["errorcode"], data["errordesc"]))
		return True

donorAccounts = DBDonorAccount()