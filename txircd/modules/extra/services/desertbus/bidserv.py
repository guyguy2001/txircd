from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.config import ConfigValidationError
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import now, stripFormatting, timestampStringFromTime, trimStringToByteLength
from zope.interface import implementer
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from os import path
from typing import Any, Callable, Dict, List, Optional, Tuple
import yaml

irc.ERR_SERVICES = "955" # Custom numeric; 955 <TYPE> <SUBTYPE> <ERROR>

# Tag list:
# - desertbus.org/auction-title
# - desertbus.org/auction-url
# - desertbus.org/auction-winners
# - desertbus.org/bid = $1500.00:bidder1:;$1269.69:bidder2:talk smack erry day;$1000:bidder3:
#   - Only winning bids are listed (the example above is for an auction with 3 winners)
# - desertbus.org/auction-state ("bid", "once", "twice", "sold", "stop")

@implementer(IPlugin, IModuleData)
class BidService(ModuleData):
	name = "BidService"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("capabilitylist", 10, self.addCapability),
			("commandpermission-AUCTIONSTART", 10, self.checkBidAdminStart),
			("commandpermission-AUCTIONSTOP", 10, self.checkBidAdminStop),
			("commandpermission-AUCTIONONCE", 10, self.checkBidAdminOnce),
			("commandpermission-AUCTIONTWICE", 10, self.checkBidAdminTwice),
			("commandpermission-AUCTIONNONCE", 10, self.checkBidAdminNonce),
			("commandpermission-AUCTIONSOLD", 10, self.checkBidAdminSold),
			("commandpermission-AUCTIONREVERT", 10, self.checkBidAdminRevert),
			("afteraccountburst", 1, self.syncAuctionData) ]
	
	def userCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("BID", 1, BidCommand(self)),
			("AUCTIONSTART", 1, AuctionStartCommand(self)),
			("AUCTIONSTOP", 1, AuctionStopCommand(self)),
			("AUCTIONONCE", 1, GoOnceCommand(self)),
			("AUCTIONTWICE", 1, GoTwiceCommand(self)),
			("AUCTIONNONCE", 1, GoNonceCommand(self)),
			("AUCTIONSOLD", 1, SoldCommand(self)),
			("AUCTIONREVERT", 1, RevertCommand(self)),
			("HIGHBIDDER", 1, HighBidderCommand(self)),
			("CURRENTAUCTION", 1, CurrentAuctionCommand(self)) ]
	
	def serverCommands(self) -> List[Tuple[str, int, Command]]:
		return [ ("BID", 1, ServerBidCommand(self)),
			("AUCTIONSTART", 1, ServerAuctionStartCommand(self)),
			("AUCTIONSTARTREQ", 1, ServerAuctionStartRequestCommand(self)),
			("AUCTIONERR", 1, ServerAuctionErrorCommand(self)),
			("AUCTIONSTOP", 1, ServerAuctionStopCommand(self)),
			("AUCTIONONCE", 1, ServerGoOnceCommand(self)),
			("AUCTIONTWICE", 1, ServerGoTwiceCommand(self)),
			("AUCTIONNONCE", 1, ServerGoNonceCommand(self)),
			("AUCTIONSOLD", 1, ServerSoldCommand(self)),
			("AUCTIONREVERT", 1, ServerRevertCommand(self)) ]
	
	def load(self) -> None:
		if "unloading-bid-tags" in self.ircd.dataCache:
			del self.ircd.dataCache["unloading-bid-tags"]
		elif "cap-add" in self.ircd.functionCache:
			self.ircd.functionCache["cap-add"]("desertbus.org/bid-tags")
	
	def unload(self) -> Optional["Deferred"]:
		self.ircd.dataCache["unloading-bid-tags"] = True
	
	def fullUnload(self) -> Optional["Deferred"]:
		del self.ircd.dataCache["unloading-bid-tags"]
		if "cap-del" in self.ircd.functionCache:
			self.ircd.functionCache["cap-del"]("desertbus.org/bid-tags")
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "donor_linked_server" in config and config["donor_linked_server"] is not None:
			if not isinstance(config["donor_linked_server"], str):
				raise ConfigValidationError("donor_linked_server", "must be a string (server name) or null")
		else:
			config["donor_linked_server"] = None
		if "bid_announce_bot" in config:
			if not isinstance(config["bid_announce_bot"], str):
				raise ConfigValidationError("bid_announce_bot", "must be a string")
		else:
			config["bid_announce_bot"] = ""
		if "bid_announce_channels" in config:
			if not isinstance(config["bid_announce_channels"], list):
				raise ConfigValidationError("bid_announce_channels", "must be a list of channel names")
			for channelName in config["bid_announce_channels"]:
				if not isinstance(channelName, str):
					raise ConfigValidationError("bid_annnounce_channels", "must be a list of channel names")
		else:
			config["bid_announce_channels"] = []
		if "bid_minimum_increment" in config:
			value = config["bid_minimum_increment"]
			try:
				if isinstance(value, int) or isinstance(value, float):
					decimalValue = Decimal(str(round(value, 2)))
				elif isinstance(value, str):
					decimalValue = Decimal(value)
				else:
					raise ConfigValidationError("bid_minimum_increment", "must be a numeric string or a float")
			except InvalidOperation:
				raise ConfigValidationError("bid_minimum_increment", "must be a numeric string or a float")
			if decimalValue.is_signed():
				raise ConfigValidationError("bid_minimum_increment", "increment must be positive")
			if not decimalValue.is_normal():
				raise ConfigValidationError("bid_minimum_increment", "must be a numeric string or a float")
		else:
			decimalValue = Decimal("0.01")
		config["bid_minimum_increment"] = decimalValue
		if "bid_going_cooldown" in config:
			if not isinstance(config["bid_going_cooldown"], int):
				raise ConfigValidationError("bid_going_cooldown", "value must be an int")
			if config["bid_going_cooldown"] < 0:
				raise ConfigValidationError("bid_going_cooldown", "value must be positive")
		else:
			config["bid_going_cooldown"] = 0
		if "bid_log_directory" in config:
			if not isinstance(config["bid_log_directory"], str):
				raise ConfigValidationError("bid_log_directory", "value must be a directory")
	
	def addCapability(self, user: "IRCUser", capList: List[str]) -> None:
		capList.append("desertbus.org/bid-tags")
	
	def checkBidAdminStart(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "command-auctionstart", users=[user]):
			return None
		return False
	
	def checkBidAdminStop(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "command-auctionstop", users=[user]):
			return None
		return False
	
	def checkBidAdminOnce(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "command-auctiononce", users=[user]):
			return None
		return False
	
	def checkBidAdminTwice(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "command-auctiontwice", users=[user]):
			return None
		return False
	
	def checkBidAdminNonce(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "command-auctionnonce", users=[user]):
			return None
		return False
	
	def checkBidAdminSold(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "command-auctionsold", users=[user]):
			return None
		return False
	
	def checkBidAdminRevert(self, user: "IRCUser", data: Dict[Any, Any]) -> Optional[bool]:
		if self.ircd.runActionUntilValue("userhasoperpermission", user, "command-auctionrevert", users=[user]):
			return None
		return False
	
	def syncAuctionData(self, server: "IRCServer") -> None:
		if "auction" not in self.ircd.storage:
			return
		auctionData = self.ircd.storage["auction"]
		server.sendMessage("AUCTIONSTART", timestampStringFromTime(auctionData["start-time"]), str(auctionData["id"]), auctionData["starting-bid"], auctionData["start-name"], auctionData["title"], prefix=self.ircd.serverID)
		for bidData in auctionData["bids"]:
			server.sendMessage("BID", timestampStringFromTime(bidData["bid-time"]), bidData["bidder-name"], bidData["bid-amount"], bidData["smack-talk"], prefix=self.ircd.serverID)
		if auctionData["state"] == "once" or auctionData["state"] == "twice":
			server.sendMessage("AUCTIONONCE", timestampStringFromTime(auctionData["state-time"]), auctionData["state-name"], prefix=self.ircd.serverID)
		if auctionData["state"] == "twice":
			server.sendMessage("AUCTIONTWICE", timestampStringFromTime(auctionData["state-time"]), auctionData["state-name"], prefix=self.ircd.serverID)
	
	def getBotAnnounceUser(self) -> Optional["IRCUser"]:
		botNick = self.ircd.config["bid_announce_bot"]
		if not botNick:
			return None
		if botNick not in self.ircd.userNicks:
			return None
		return self.ircd.userNicks[botNick]
	
	def sendMessageFromBot(self, toUser: "IRCUser", command: str, *args: str, **kw: Dict[str, Any]) -> None:
		responseBot = self.getBotAnnounceUser()
		if not responseBot:
			toUser.sendMessage(command, *args, **kw)
			return
		kw["prefix"] = responseBot.hostmask()
		toUser.sendMessage(command, *args, **kw)
	
	def sendErrorToLocalOrRemoteUser(self, user: "IRCUser", errorCode: str, errorDescription: str) -> None:
		if not user:
			return
		if user.uuid not in self.ircd.users:
			return
		if user.uuid[:3] == self.ircd.serverID:
			user.sendMessage(irc.ERR_SERVICES, "BID", errorCode, errorDescription)
			self.sendMessageFromBot("NOTICE", errorDescription)
		else:
			userServer = self.ircd.servers[user.uuid[:3]]
			userServer.sendMessage("AUCTIONERR", user.uuid, errorCode, errorDescription)
	
	def announce(self, messageToAnnounce: str, conditionalTags: Dict[str, Tuple[str, Callable[["IRCUser"], bool]]]) -> None:
		botUser = self.getBotAnnounceUser()
		msgPrefix = self.ircd.name
		if botUser:
			msgPrefix = botUser.hostmask()
		for channelName in self.ircd.config["bid_announce_channels"]:
			if channelName in self.ircd.channels:
				self.ircd.channels[channelName].sendUserMessage("PRIVMSG", messageToAnnounce, prefix=msgPrefix, conditionalTags=conditionalTags)
	
	def conditionalTagsFilter(self, user: "IRCUser") -> bool:
		if "capabilities" in user.cache and "desertbus.org/bid-tags" in user.cache["capabilities"]:
			return True
		return False
	
	def bidTagValue(self) -> str:
		if "auction" not in self.ircd.storage:
			return ""
		auctionData = self.ircd.storage["auction"]
		if not auctionData["bids"]:
			return ""
		numWinners = auctionData["winners"]
		bidStringParts = []
		for bidData in list(reversed(auctionData["bids"]))[:numWinners]:
			bidStringParts.append("{}:{}:{}".format(bidData["bid-amount"], bidData["bidder-name"], self.escapeSmackTalk(bidData["smack-talk"])))
		return ";".join(bidStringParts)
	
	def escapeSmackTalk(self, smackTalk: str) -> str:
		return smackTalk.replace("\\", "\\\\").replace(";", "\\,").replace(":", "\\.")
	
	def lastBidTime(self) -> Optional[datetime]:
		if "auction" not in self.ircd.storage:
			return None
		auctionData = self.ircd.storage["auction"]
		if not auctionData["bids"]:
			return None
		lastBidTime = auctionData["bids"][0]["bid-time"]
		for bidData in auctionData["bids"][1:]:
			if bidData["bid-time"] > lastBidTime:
				lastBidTime = bidData["bid-time"]
		return lastBidTime
	
	def startAuctionFromDatabase(self, auctionID: int, startingUser: Optional["IRCUser"]) -> None:
		if "auction" in self.ircd.storage:
			self.sendErrorToLocalOrRemoteUser(startingUser, "INPROGRESS", "An auction is already in progress.")
			return
		resultDeferred = self.ircd.runActionUntilValue("donordatabasequery", "SELECT id, name, sold, starting_bid FROM prizes WHERE id = %s", auctionID)
		if resultDeferred is None:
			self.sendErrorToLocalOrRemoteUser(startingUser, "NODATA", "Couldn't get information from the database. Please try again later.")
			return
		resultDeferred.addCallbacks(callback=self.finishStartAuction, callbackArgs=(startingUser,), errback=self.errorStartAuction, errbackArgs=(startingUser,))
	
	def finishStartAuction(self, result: List[Tuple[int, str, int, Decimal]], user: Optional["IRCUser"]) -> None:
		if not result:
			self.sendErrorToLocalOrRemoteUser(user, "ITEMNOTFOUND", "No item with the given ID was found.")
			return
		resultRow = result[0]
		auctionID, auctionTitle, isSold, startingBid = resultRow
		if isSold > 0:
			self.sendErrorToLocalOrRemoteUser(user, "ALREADYSOLD", "The item is already sold!")
			return
		if self.ircd.storage["auction"]:
			self.sendErrorToLocalOrRemoteUser(user, "INPROGRESS", "An auction is already in progress.")
			return
		self.startAuction(auctionID, auctionTitle, startingBid, now(), user, None)
	
	def errorStartAuction(self, error: "Failure", user: "IRCUser") -> None:
		self.sendErrorToLocalOrRemoteUser(user, "NODATA", "Couldn't get information from the database. Please try again later.")
	
	def startAuction(self, auctionID: int, auctionTitle: str, startingBid: Decimal, startTime: datetime, startingUser: Optional["IRCUser"], starterName: Optional[str], fromServer: "IRCServer" = None) -> None:
		if not starterName:
			if startingUser:
				starterName = startingUser.nick
			else:
				starterName = "?"
		self.ircd.storage["auction"] = {
			"id": auctionID,
			"title": auctionTitle,
			"state": "bid",
			"starting-bid": startingBid,
			"winners": 1,
			"bids": [],
			"start-time": startTime,
			"state-time": startTime,
			"start-name": starterName,
			"state-name": starterName
		}
		
		announceTags = {
			"desertbus.org/auction-title": (auctionTitle, self.conditionalTagsFilter),
			"desertbus.org/auction-url": ("https://desertbus.org/live-auction/{}".format(auctionID), self.conditionalTagsFilter),
			"desertbus.org/auction-winners": ("1", self.conditionalTagsFilter)
		}
		self.announce("\x02\x0312Starting auction for \x0304{}\x0312! (Initiated by {}) - Bid with \x033/bid $amount Smack talk!".format(auctionTitle, starterName), announceTags)
		self.announce("\x02\x034You must be logged into your Desert Bus donor account to bid! https://desertbus.org/donor")
		self.announce("\x02\x034Fake bids will not be tolerated!")
		self.announce("\x02\x0312Bidding begins at ${} with a minimum increment of ${}".format(startingBid, self.ircd.config["bid_minimum_increment"]))
		if startingUser:
			broadcastPrefix = startingUser.uuid
		elif fromServer:
			broadcastPrefix = fromServer.serverID
		else:
			broadcastPrefix = self.ircd.serverID
		self.ircd.broadcastToServers(fromServer, "AUCTIONSTART", timestampStringFromTime(startTime), str(auctionID), str(startingBid), starterName, auctionTitle, prefix=broadcastPrefix)
	
	def cancelAuction(self, cancelingUser: Optional["IRCUser"], fromServer: "IRCServer" = None) -> None:
		if "auction" not in self.ircd.storage:
			self.sendErrorToLocalOrRemoteUser(cancelingUser, "NOAUCTION", "An auction is not in progress.")
			return
		announceTags = {
			"desertbus.org/auction-state": ("stop", self.conditionalTagsFilter)
		}
		self.announce("\x02\x034Auction canceled! (Canceled by {})".format(cancelingUser.nick if cancelingUser else "?"), announceTags)
		startTime = self.ircd.storage["auction"]["start-time"]
		del self.ircd.storage["auction"]
		if cancelingUser:
			broadcastPrefix = cancelingUser.uuid
		elif fromServer:
			broadcastPrefix = fromServer.serverID
		else:
			broadcastPrefix = self.ircd.serverID
		self.ircd.broadcastToServers(fromServer, "AUCTIONSTOP", timestampStringFromTime(startTime), prefix=broadcastPrefix)
	
	def goOnce(self, changingUser: Optional["IRCUser"], changeByName: Optional[str], stateTime: datetime, fromServer: "IRCServer" = None) -> None:
		if "auction" not in self.ircd.storage:
			self.sendErrorToLocalOrRemoteUser(changingUser, "NOAUCTION", "An auction is not in progress.")
			return
		if self.ircd.storage["auction"]["state"] != "bid":
			self.sendErrorToLocalOrRemoteUser(changingUser, "BADSTATE", "The auction is not in the correct state to go once.")
			return
		checkAgainstTime = stateTime - timedelta(seconds=self.ircd.config["bid_going_cooldown"])
		if self.lastBidTime() > checkAgainstTime:
			self.sendErrorToLocalOrRemoteUser(changingUser, "GOINGCOOLDOWN", "The last bid happened too recently to go once.")
			return
		announceTags = {
			"desertbus.org/auction-state": ("once", self.conditionalTagsFilter)
		}
		if not changeByName:
			if changingUser:
				changeByName = changingUser.nick
			else:
				changeByName = "?"
		self.announce("\x02\x0312Going once! (from {})".format(changeByName), announceTags)
		self.ircd.storage["auction"]["state"] = "once"
		self.ircd.storage["auction"]["state-time"] = stateTime
		self.ircd.storage["auction"]["state-name"] = changeByName
		if changingUser:
			broadcastPrefix = changingUser.uuid
		elif fromServer:
			broadcastPrefix = fromServer.serverID
		else:
			broadcastPrefix = self.ircd.serverID
		self.ircd.broadcastToServers(fromServer, "AUCTIONONCE", timestampStringFromTime(stateTime), changeByName, prefix=broadcastPrefix)
	
	def goTwice(self, changingUser: Optional["IRCUser"], changeByName: Optional[str], stateTime: datetime, fromServer: "IRCServer" = None) -> None:
		if "auction" not in self.ircd.storage:
			self.sendErrorToLocalOrRemoteUser(changingUser, "NOAUCTION", "An auction is not in progress.")
			return
		if self.ircd.storage["auction"]["state"] != "once":
			self.sendErrorToLocalOrRemoteUser(changingUser, "BADSTATE", "The auction is not in the correct state to go twice.")
			return
		announceTags = {
			"desertbus.org/auction-state": ("twice", self.conditionalTagsFilter)
		}
		if not changeByName:
			if changingUser:
				changeByName = changingUser.nick
			else:
				changeByName = "?"
		self.announce("\x02\x0312Going twice! (from {})".format(changeByName), announceTags)
		self.ircd.storage["auction"]["state"] = "twice"
		self.ircd.storage["auction"]["state-time"] = stateTime
		self.ircd.storage["auction"]["state-name"] = changeByName
		if changingUser:
			broadcastPrefix = changingUser.uuid
		elif fromServer:
			broadcastPrefix = fromServer.serverID
		else:
			broadcastPrefix = self.ircd.serverID
		self.ircd.broadcastToServers(fromServer, "AUCTIONTWICE", timestampStringFromTime(stateTime), changeByName, prefix=broadcastPrefix)
	
	def goNonce(self, changingUser: Optional["IRCUser"], changeByName: Optional[str], stateTime: datetime, fromServer: "IRCServer" = None) -> None:
		if "auction" not in self.ircd.storage:
			self.sendErrorToLocalOrRemoteUser(changingUser, "NOAUCTION", "An auction is not in progress.")
			return
		if self.ircd.storage["auction"]["state"] == "bid":
			self.sendErrorToLocalOrRemoteUser(changingUser, "BADSTATE", "The auction is already in the normal bidding state.")
			return
		announceTags = {
			"desertbus.org/auction-state": ("bid", self.conditionalTagsFilter)
		}
		if not changeByName:
			if changingUser:
				changeByName = changingUser.nick
			else:
				changeByName = "?"
		self.announce("\x02\x034Reverting going once (from {})".format(changeByName), announceTags)
		self.ircd.storage["auction"]["state"] = "bid"
		self.ircd.storage["auction"]["state-time"] = stateTime
		self.ircd.storage["auction"]["state-name"] = changeByName
		if changingUser:
			broadcastPrefix = changingUser.uuid
		elif fromServer:
			broadcastPrefix = fromServer.serverID
		else:
			broadcastPrefix = self.ircd.serverID
		self.ircd.broadcastToServers(fromServer, "AUCTIONNONCE", timestampStringFromTime(stateTime), changeByName, prefix=broadcastPrefix)
	
	def sold(self, sellingUser: Optional["IRCUser"], sellerName: Optional[str], fromServer: "IRCServer" = None) -> None:
		if "auction" not in self.ircd.storage:
			self.sendErrorToLocalOrRemoteUser(sellingUser, "NOAUCTION", "An auction is not in progress.")
			return
		if not fromServer and self.ircd.storage["auction"]["state"] != "twice":
			self.sendErrorToLocalOrRemoteUser(sellingUser, "BADSTATE", "The auction is not in the correct state to sell.")
			return
		if not self.ircd.storage["auction"]["bids"]:
			self.sendErrorToLocalOrRemoteUser(sellingUser, "NOBIDS", "There were no bids in the auction! (Did you want to cancel instead?")
			return
		announceTags = {
			"desertbus.org/auction-state": ("sold", self.conditionalTagsFilter)
		}
		if not sellerName:
			if sellingUser:
				sellerName = sellingUser.nick
			else:
				sellerName = "?"
		self.announce("\x02\x033SOLD! (Sold by {})".format(sellerName), announceTags)
		auctionData = self.ircd.storage["auction"]
		winningBidData = auctionData["bids"][-1]
		del self.ircd.storage["auction"]
		if not self.ircd.runActionUntilTrue("donordatabaseoperate", "UPDATE prizes SET donor_id = %s, sold_amount = %s, sold = 1 WHERE id = %s", winningBidData["bidder-id"], winningBidData["bid-amount"], self.ircd.storage["auction"]["id"]):
			self.sendErrorToLocalOrRemoteUser(sellingUser, "NOSAVE", "Couldn't save results to database. Check the server log for results.")
		if "bid_log_directory" in self.ircd.config:
			logFileName = path.join(self.ircd.config["bid_log_directory"], "{}.yaml".format(auctionData["id"]))
			try:
				with open(logFileName, "w") as logFile:
					yaml.dump(auctionData, logFile, default_flow_style=False)
			except IOError:
				self.sendErrorToLocalOrRemoteUser(sellingUser, "AUCTIONLOG", "Could not write auction log file on server {}".format(self.ircd.name))
		if sellingUser:
			broadcastPrefix = sellingUser.uuid
		elif fromServer:
			broadcastPrefix = fromServer.serverID
		else:
			broadcastPrefix = self.ircd.serverID
		self.ircd.broadcastToServers(fromServer, "AUCTIONSOLD", sellerName, prefix=broadcastPrefix)
	
	def bid(self, biddingUser: Optional["IRCUser"], accountName: Optional[str], bidAmount: Decimal, smackTalk: str, bidTime: datetime, fromServer: "IRCServer" = None) -> None:
		if "auction" not in self.ircd.storage:
			self.sendErrorToLocalOrRemoteUser(biddingUser, "NOAUCTION", "An auction is not in progress.")
			return
		bidAmount = bidAmount.quantize(Decimal(".01"))
		auctionData = self.ircd.storage["auction"]
		auctionWinners = auctionData["winners"]
		if len(auctionData["bids"]) >= auctionWinners:
			minimumBid = auctionData["bids"][-auctionWinners]["bid-amount"]
			minimumBid += self.ircd.config["bid_minimum_increment"]
		else:
			minimumBid = auctionData["starting-bid"]
		minimumBid = minimumBid.quantize(Decimal(".01"))
		announceBid = True
		if bidAmount < minimumBid:
			if fromServer:
				announceBid = False
			else:
				self.sendErrorToLocalOrRemoteUser(biddingUser, "LOWBID", "You didn't bid high enough! You must bid at least ${} to bid.".format(minimumBid))
				return
		if biddingUser and not accountName:
			accountName = biddingUser.metadataValue("account")
		if not accountName:
			self.sendErrorToLocalOrRemoteUser(biddingUser, "NOTLOGIN", "You must be logged into your donor account to bid.")
			return
		donorID = self.ircd.runActionUntilValue("accountgetmetadatavalue", accountName, "donorid")
		if not donorID:
			self.sendErrorToLocalOrRemoteUser(biddingUser, "NOTDONOR", "Your account isn't associated with a donor account.")
			return
		smackTalk = stripFormatting(smackTalk)
		smackTalk = trimStringToByteLength(smackTalk, 200)
		announceTags = {}
		if auctionData["state"] != "bid":
			announceTags["desertbus.org/auction-state"] = ("bid", self.conditionalTagsFilter)
			auctionData["state"] = "bid"
			auctionData["state-time"] = bidTime
			auctionData["state-name"] = auctionData["start-name"]
		bidData = {
			"bid-amount": bidAmount,
			"bidder-id": donorID,
			"bidder-name": biddingUser.nick,
			"smack-talk": smackTalk,
			"bid-time": bidTime
		}
		if not auctionData["bids"]:
			auctionData["bids"].append(bidData)
		elif bidAmount > auctionData["bids"][-1]["bid-amount"]:
			auctionData["bids"].append(bidData)
		else:
			for index, otherBidData in list(reversed(list(enumerate(auctionData["bids"]))))[1:]:
				if bidAmount > otherBidData["bid-amount"]:
					auctionData["bids"].insert(index + 1, bidData)
					break
			else:
				auctionData["bids"].insert(0, bidData)
		if announceBid:
			announceTags["desertbus.org/bid"] = (self.bidTagValue(), self.conditionalTagsFilter)
			self.announce("\x02\x0303{} has bid ${}! \x0304{}".format(biddingUser.nick, bidAmount, smackTalk), announceTags)
		if biddingUser:
			broadcastPrefix = biddingUser.uuid
		elif fromServer:
			broadcastPrefix = fromServer.serverID
		else:
			broadcastPrefix = self.ircd.serverID
		self.ircd.braodcastToServers(fromServer, "BID", timestampStringFromTime(bidTime), accountName, str(bidAmount), smackTalk, prefix=broadcastPrefix)
	
	def revertBid(self, bidAmount: Decimal, revertingUser: Optional["IRCUser"], reverterName: Optional[str], fromServer: "IRCServer" = None) -> None:
		if "auction" not in self.ircd.storage:
			self.sendErrorToLocalOrRemoteUser(revertingUser, "NOAUCTION", "An auction is not in progress.")
			return
		bidIndex = None
		bidData = None
		auctionData = self.ircd.storage["auction"]
		for index, thisBidData in enumerate(auctionData["bids"]):
			if thisBidData["bid-amount"] == bidAmount:
				bidIndex = index
				bidData = thisBidData
				break
		else:
			self.sendErrorToLocalOrRemoteUser(revertingUser, "BADAMOUNT", "That bid amount doesn't match any bids.")
			return
		del auctionData["bids"][bidIndex]
		bidderName = bidData["bidder-name"]
		announceTags = {
			"desertbus.org/bid": (self.bidTagValue(), self.conditionalTagsFilter)
		}
		if not reverterName:
			if revertingUser:
				reverterName = revertingUser.nick
			else:
				reverterName = "?"
		if not auctionData["bids"]:
			self.announce("\x02\x034Removed bid of ${} by {}. Starting bid is ${}. (Reverted by {})".format(bidAmount, bidderName, auctionData["starting-bid"], reverterName), announceTags)
		elif auctionData["winners"] == 1:
			highBidData = self.ircd.storage["auction"]["bids"][-1]
			self.announce("\x02\x034Removed bid of ${} by {}. Current high bid is ${} by {}. (Reverted by {})".format(bidAmount, bidderName, highBidData["bid-amount"], highBidData["bidder-name"], reverterName), announceTags)
		else:
			self.announce("\x02\x034Removed bid of ${} by {}. (Reverted by {}) Current high bids:".format(bidAmount, bidderName, reverterName), announceTags)
			for highBidData in list(reversed(auctionData["bids"]))[:auctionData["winners"]]:
				self.announce("\x02\x033High bid: ${} by {}".format(highBidData["bid-amount"], highBidData["bidder-name"]))
		if revertingUser:
			broadcastPrefix = revertingUser.uuid
		elif fromServer:
			broadcastPrefix = fromServer.serverID
		else:
			broadcastPrefix = self.ircd.serverID
		self.ircd.broadcastToServers(fromServer, "AUCTIONREVERT", str(bidAmount), reverterName, prefix=broadcastPrefix)

@implementer(ICommand)
class BidCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			user.sendSingleError("BidParams", irc.ERR_NEEDMOREPARAMS, "BID", "Not enough parameters")
			return None
		bidAmountStr = params[0]
		bidAmountStr = bidAmountStr.lstrip("$")
		bidAmount = None
		try:
			bidAmount = Decimal(bidAmountStr)
		except InvalidOperation:
			user.startErrorBatch("BidAmount")
			user.sendBatchedError("BidAmount", irc.ERR_SERVICES, "BID", "BADAMOUNT", "You must bid a number of dollars.")
			botUser = self.module.getBotAnnounceUser()
			if botUser:
				user.sendBatchedError("BidAmount", "NOTICE", "You must bid a number of dollars.", prefix=botUser.hostmask())
			else:
				user.sendBatchedError("BidAmount", "NOTICE", "You must bid a number of dollars.")
			return None
		if len(params) == 1:
			return {
				"bid": bidAmount
			}
		return {
			"bid": bidAmount,
			"smacktalk": " ".join(params[1:])
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if "smacktalk" in data:
			self.module.bid(user, None, data["bid"], data["smacktalk"], now())
		else:
			self.module.bid(user, None, data["bid"], "", now())
		return True

@implementer(ICommand)
class AuctionStartCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) < 1:
			user.sendSingleError("AuctionStartCmdParams", irc.ERR_NEEDMOREPARAMS, "AUCTIONSTART", "Not enough parameters")
			return None
		auctionID = None
		try:
			auctionID = int(params[0])
		except ValueError:
			user.startErrorBatch("AuctionStartID")
			user.sendBatchedError("AuctionStartID", irc.ERR_SERVICES, "BID", "STARTID", "The auction ID must be a number.")
			botUser = self.module.getBotAnnounceUser()
			if botUser:
				user.sendBatchedError("AuctionStartID", "NOTICE", "The auction ID must be a number.", prefix=botUser.hostmask())
			else:
				user.sendBatchedError("AuctionStartID", "NOTICE", "The auction ID must be a number.")
			return None
		return {
			"auctionid": auctionID
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		auctionID = data["auctionid"]
		handleServerName = self.ircd.config["donor_linked_server"]
		if handleServerName:
			if handleServerName not in self.ircd.serverNames:
				user.sendMessage(irc.ERR_SERVICES, "BID", "NOSERVER", "Could not contact the database server.")
				self.module.sendMessageFromBot(user, "NOTICE", "Could not contact the database server.")
				return True
			handleServer = self.ircd.serverNames[handleServerName]
			handleServer.sendMessage("AUCTIONSTARTREQ", handleServer.serverID, str(auctionID), prefix=user.uuid)
			return True
		self.module.startAuctionFromDatabase(auctionID, user)
		return True

@implementer(ICommand)
class AuctionStopCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		self.module.cancelAuction(user)
		return True

@implementer(ICommand)
class GoOnceCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		self.module.goOnce(user, None, now())
		return True

@implementer(ICommand)
class GoTwiceCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		self.module.goTwice(user, None, now())
		return True

@implementer(ICommand)
class GoNonceCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		self.module.goNonce(user, None, now())
		return True

@implementer(ICommand)
class SoldCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		self.module.sold(user, None)
		return True

@implementer(ICommand)
class RevertCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if not params or not params[0]:
			return {}
		revertAmountStr = params[0]
		revertAmount = None
		try:
			revertAmount = Decimal(revertAmountStr)
		except InvalidOperation:
			user.startErrorBatch("RevertAmount")
			user.sendBatchedError("RevertAmount", irc.ERR_SERVICES, "BID", "BADAMOUNT", "You must enter a bid amount (as the numeric amount) to revert.")
			botUser = self.module.getBotAnnounceUser()
			if botUser:
				user.sendBatchedError("RevertAmount", "NOTICE", "You must enter a bid amount (as the numeric amount) to revert.", prefix=botUser.hostmask())
			else:
				user.sendBatchedError("RevertAmount", "NOTICE", "You must enter a bid amount (as the numeric amount) to revert.")
			return None
		return {
			"amount": revertAmount
		}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if "amount" in data:
			revertAmount = data["amount"]
		else:
			if "auction" not in self.ircd.storage:
				self.module.sendErrorToLocalOrRemoteUser(user, "NOAUCTION", "An auction is not in progress.")
				return True
			if not self.ircd.storage["auction"]["bids"]:
				self.module.sendErrorToLocalOrRemoteUser(user, "NOBIDS", "There are no bids to revert.")
				return True
			revertAmount = self.ircd.storage["auction"]["bids"][-1]["bid-amount"]
		self.module.revertBid(revertAmount, user)
		return True

@implementer(ICommand)
class HighBidderCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if "auction" not in self.ircd.storage:
			self.module.sendErrorToLocalOrRemoteUser(user, "NOAUCTION", "An auction is not in progress.")
			return True
		auctionData = self.ircd.storage["auction"]
		if not auctionData["bids"]:
			self.module.sendErrorToLocalOrRemoteUser(user, "NOBIDS", "There are no bids yet.")
			return True
		announceTags = {
			"desertbus.org/bid": (self.module.bidTagValue(), self.module.conditionalTagsFilter)
		}
		highestBids = []
		numWinners = auctionData["winners"]
		for bidData in list(reversed(auctionData["bids"]))[:numWinners]:
			highestBids.append("${} from {}".format(bidData["bid-amount"], bidData["bidder-name"]))
		if numWinners == 1:
			displayString = "Highest bid: {}".format(", ".join(highestBids))
		else:
			displayString = "Highest bids: {}".format(", ".join(highestBids))
		botUser = self.module.getBotAnnounceUser()
		announceTags = user.filterConditionalTags(announceTags)
		if botUser:
			user.sendMessage("NOTICE", displayString, prefix=botUser.hostmask(), tags=announceTags)
		else:
			user.sendMessage("NOTICE", displayString, tags=announceTags)
		return True

@implementer(ICommand)
class CurrentAuctionCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, user: "IRCUser", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		return {}
	
	def execute(self, user: "IRCUser", data: Dict[Any, Any]) -> bool:
		if "auction" not in self.ircd.storage:
			self.module.sendErrorToLocalOrRemoteUser(user, "NOAUCTION", "An auction is not in progress.")
			return True
		auctionData = self.ircd.storage["auction"]
		botUser = self.module.getBotAnnounceUser()
		auctionLine = "Current auction: {}".format(auctionData["title"])
		if auctionData["state"] == "once":
			auctionLine = "{} (Going once!)".format(auctionLine)
		elif auctionData["state"] == "twice":
			auctionLine = "{} (Going twice!)".format(auctionLine)
		if self.module.conditionalTagsFilter(user):
			auctionTags = {
				"auction-title": auctionData["title"],
				"auction-url": "https://desertbus.org/live-auction/{}".format(auctionData["id"]),
				"auction-winners": str(auctionData["winners"]),
				"auction-state": auctionData["state"]
			}
		else:
			auctionTags = {}
		if botUser:
			user.sendMessage("NOTICE", auctionLine, prefix=botUser.hostmask(), tags=auctionTags)
		else:
			user.sendMessage("NOTICE", auctionLine, tags=auctionTags)
		return True

@implementer(ICommand)
class ServerBidCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 4:
			return None
		returnData = {}
		if prefix in self.ircd.users:
			returnData["fromuser"] = self.ircd.users[prefix]
		try:
			returnData["bidtime"] = datetime.utcfromtimestamp(float(params[0]))
		except (ValueError, OverflowError):
			return None
		accountName = params[1]
		if not self.ircd.runActionUntilValue("checkaccountexists", accountName):
			return None
		returnData["account"] = accountName
		try:
			returnData["amount"] = Decimal(params[2])
		except InvalidOperation:
			return None
		returnData["smacktalk"] = params[3]
		return returnData
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.bid(data["fromuser"], data["account"], data["amount"], data["smacktalk"], data["bidtime"], server)
		return True

@implementer(ICommand)
class ServerAuctionStartCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 5:
			return None
		startTime = None
		try:
			startTime = datetime.utcFromTimestamp(float(params[0]))
		except (ValueError, OverflowError):
			return None
		auctionID = None
		try:
			auctionID = int(params[1])
		except ValueError:
			return None
		startingBid = None
		try:
			startingBid = Decimal(params[2])
		except InvalidOperation:
			return None
		if prefix in self.ircd.users:
			startingUser = self.ircd.users[prefix]
		else:
			startingUser = None
		return {
			"auctionid": auctionID,
			"starttime": startTime,
			"startbid": startingBid,
			"startuser": startingUser,
			"startname": params[3],
			"title": params[4]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "auction" in self.ircd.storage:
			existingAuctionData = self.ircd.storage["auction"]
			if existingAuctionData["start-time"] < data["startuser"]:
				return True
			self.module.cancelAuction(None, server)
		self.module.startAuction(data["auctionid"], data["title"], data["startbid"], data["starttime"], data["startuser"], data["startname"], server)
		return True

@implementer(ICommand)
class ServerAuctionStartRequestCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		if prefix not in self.ircd.users:
			return None
		auctionID = None
		try:
			auctionID = int(params[1])
		except ValueError:
			return None
		if params[0] != self.ircd.serverID and params[0] not in self.ircd.servers:
			return None
		return {
			"fromsuer": self.ircd.users[prefix],
			"toserverid": params[0],
			"auctionid": auctionID
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if data["toserverid"] == self.ircd.serverID:
			self.module.startAuctionFromDatabase(data["auctionid"], data["fromuser"])
			return True
		server = self.ircd.servers[data["toserverid"]]
		server.sendMessage("AUCTIONSTARTREQ", server.serverID, str(data["auctionid"]), prefix=data["fromuser"].uuid)
		return True

@implementer(ICommand)
class ServerAuctionErrorCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 3:
			return None
		if params[0] not in self.ircd.users:
			if params[0] in self.ircd.recentlyQuitUsers:
				return {
					"lostuser": True
				}
			return None
		return {
			"user": self.ircd.users[params[0]],
			"errcode": params[1],
			"errdesc": params[2]
		}
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "lostuser" in data:
			return True
		user = data["user"]
		errCode = data["errcode"]
		errDescription = data["errdesc"]
		if user.uuid[:3] == self.ircd.serverID:
			user.sendMessage(irc.ERR_SERVICES, "BID", errCode, errDescription)
			self.module.sendMessageFromBot(user, "NOTICE", errDescription)
			return True
		userServer = self.ircd.servers[user.uuid[:3]]
		userServer.sendMessage("AUCTIONERR", user.uuid, errCode, errDescription, prefix=self.ircd.serverID)
		return True

@implementer(ICommand)
class ServerAuctionStopCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 1:
			return None
		returnData = {}
		try:
			returnData["auctiontime"] = datetime.utcfromtimestamp(float(params[0]))
		except (ValueError, OverflowError):
			return None
		if prefix in self.ircd.users:
			returnData["user"] = self.ircd.users[prefix]
		else:
			returnData["user"] = None
		return returnData
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		if "auction" not in self.ircd.storage:
			return None
		auctionData = self.ircd.storage["auction"]
		if auctionData["start-time"] != data["auctiontime"]:
			return True
		self.module.cancelAuction(data["user"], server)
		return True

@implementer(ICommand)
class ServerGoOnceCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		returnData = {}
		try:
			returnData["time"] = datetime.utcfromtimestamp(float(params[0]))
		except (ValueError, OverflowError):
			return None
		returnData["name"] = params[1]
		if prefix in self.ircd.users:
			returnData["user"] = self.ircd.users[prefix]
		else:
			returnData["user"] = None
		return returnData
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.goOnce(data["user"], data["name"], data["time"], server)
		return True

@implementer(ICommand)
class ServerGoTwiceCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		returnData = {}
		try:
			returnData["time"] = datetime.utcfromtimestamp(float(params[0]))
		except (ValueError, OverflowError):
			return None
		returnData["name"] = params[1]
		if prefix in self.ircd.users:
			returnData["user"] = self.ircd.users[prefix]
		else:
			returnData["user"] = None
		return returnData
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.goTwice(data["user"], data["name"], data["time"], server)
		return True

@implementer(ICommand)
class ServerGoNonceCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		returnData = {}
		try:
			returnData["time"] = datetime.utcfromtimestamp(float(params[0]))
		except (ValueError, OverflowError):
			return None
		returnData["name"] = params[1]
		if prefix in self.ircd.users:
			returnData["user"] = self.ircd.users[prefix]
		else:
			returnData["user"] = None
		return returnData
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.goNonce(data["user"], data["name"], data["time"], server)
		return True

@implementer(ICommand)
class ServerSoldCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 1:
			return None
		returnData = {}
		if prefix in self.ircd.users:
			returnData["user"] = self.ircd.users[prefix]
		else:
			returnData["user"] = None
		returnData["name"] = params[0]
		return returnData
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.sold(data["user"], data["name"], server)
		return True

@implementer(ICommand)
class ServerRevertCommand(Command):
	def __init__(self, module: BidService):
		self.module = module
		self.ircd = module.ircd
	
	def parseParams(self, server: "IRCServer", params: List[str], prefix: str, tags: Dict[str, Optional[str]]) -> Optional[Dict[Any, Any]]:
		if len(params) != 2:
			return None
		returnData = {}
		try:
			returnData["amount"] = Decimal(params[0])
		except InvalidOperation:
			return None
		returnData["name"] = params[1]
		if prefix in self.ircd.users:
			returnData["user"] = self.ircd.users[prefix]
		else:
			returnData["user"] = None
		return returnData
	
	def execute(self, server: "IRCServer", data: Dict[Any, Any]) -> bool:
		self.module.revertBid(data["amount"], data["user"], data["name"], server)
		return True

bidServ = BidService()