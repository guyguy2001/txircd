from twisted.enterprise.adbapi import ConnectionPool
from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implementer
from typing import Any, Callable, Dict, List, Optional, Tuple

@implementer(IPlugin, IModuleData)
class DBDonorDatabase(ModuleData):
	name = "DBDonorDatabase"
	
	def actions(self) -> List[Tuple[str, int, Callable]]:
		return [ ("donordatabasequery", 1, self.queryDatabase),
			("donordatabaseoperate", 1, self.operateDatabase) ]
	
	def load(self) -> None:
		self.db = None
		dbConfig = self.ircd.config["donor_db"]
		if dbConfig:
			self.db = ConnectionPool("pymysql", **dbConfig)
		self.queryID = 0
		self.pendingResponses = {}
	
	def unload(self) -> None:
		self.db.close()
	
	def rehash(self) -> None:
		self.db.close()
		self.db = None
		dbConfig = self.ircd.config["donor_db"]
		if dbConfig:
			self.db = ConnectionPool("pymysql", **dbConfig)
	
	def verifyConfig(self, config: Dict[str, Any]) -> None:
		if "donor_db" in config:
			if not isinstance(config["donor_db"], dict):
				raise ConfigValidationError("donor_db", "must be a dict")
			for keyName in ("host", "port", "database", "user", "password"):
				if keyName not in config["donor_db"]:
					raise ConfigValidationError("donor_db", "does not contain the required entry \"{}\"".format(keyName))
				if not isinstance(config["donor_db"][keyName], str):
					raise ConfigValidationError("donor_db", "value for key \"{}\" is not a string".format(keyName))
		else:
			config["donor_db"] = None
	
	def queryDatabase(self, query: str, *args: str) -> Optional["Deferred"]:
		"""
		Runs the query given and returns a deferred that is called back with the result.
		Returns None if the query fails to run.
		"""
		if self.db:
			return self.db.runQuery(query, *args)
		return None
	
	def operateDatabase(self, query: str, *args: str) -> Optional[bool]:
		"""
		Runs the database operation given and returns a boolean indicating whether it actually ran.
		"""
		if self.db:
			self.db.runOperation(query, *args)
			return True
		return None

database = DBDonorDatabase()