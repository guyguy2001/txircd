from twisted.enterprise import adbapi
from twisted.python import log
import logging

from service import Service

class DBService(Service):
    """A subclass of service that builds in a MySQL database connection and some helpers."""

    db = None
    db_config_defaults = {
        "host": "localhost",
        "port": 3306,
        "dbname": "txircd",
        "user": "txircd",
        "password": "txircd",
    }

    def load(self):
        super(DBService, self).load()
        db_config = self.db_config_defaults.copy()
        db_config.update(self.ircd.config.getWithDefault('database', {}))
        self.db = adbapi.ConnectionPool(
            "pymysql",
            host=db_config["host"],
            port=db_config["port"],
            db=db_config["dbname"],
            user=db_config["user"],
            passwd=db_config["password"],
            cp_min=1,
            cp_max=1,
            cp_reconnect=True,
        )

    def unload(self):
        if self.db:
            self.db.close()

    def query(self, callback, errback, queryString, *args):
        """Make a query to the database.
        Calls callback(rows) when results are ready,
        or errback(error) if it fails.
        If errback is None, errors are logged and ignored."""
        deferred = self.db.runQuery(queryString, args)
        if callback:
            deferred.addCallback(callback)
        def checkErrorForRetry(failure):
            failure.trap(adbapi.ConnectionLost)
            self.query(callback, errback, queryString, *args)
        deferred.addErrback(checkErrorForRetry)
        if errback:
            deferred.addErrback(errback)

    def queryGetOne(self, callback, errback, queryString, *args):
        """As per query(), but callback takes only one row as an arg,
        or None if no rows were returned.
        Raises an error if multiple rows returned."""
        def getOneRow(rows):
            if not rows:
                callback(None)
            elif len(rows) == 1:
                callback(rows[0])
            else:
                raise ValueError("Database query returned more than one row: {!r} with args {}".format(queryString, args))
        self.query(getOneRow, errback, queryString, *args)

    def reportError(self, user, message="Server error", detail=False, serverLog=True):
        """Returns an errback to pass to query() which reports an error to the given user.
        The message may be customised. If detail=True, error details are appended to the message.
        If serverLog=True, also log a warning message to the server log."""
        def _reportError(failure):
            self.tellUser(user, "{}: {}".format(message, failure.getErrorMessage()) if detail else message)
            if serverLog:
                log.msg("An error occurred during a service operation: {}\n{}".format(
                        message, failure.getTraceback()), logLevel=logging.WARNING)
        return _reportError
