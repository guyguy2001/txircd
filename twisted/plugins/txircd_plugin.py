from signal import signal, SIGHUP
from twisted.application.service import IServiceMaker
from twisted.plugin import IPlugin
from twisted.python import log, usage
from zope.interface import implements

from txircd.ircd import IRCd

class Options(usage.Options):
    optParameters = [["config", "c", "txircd.yaml", "The configuration file to read"]]

class IRCdServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "txircd"
    description = "Twisted IRC Server"
    options = Options
    
    def makeService(self, options):
        ircd = IRCd(options["config"])
        signal(SIGHUP, lambda signal, stack: ircd.rehash())
        return ircd

observer = log.PythonLoggingObserver()
observer.start()

txircd = IRCdServiceMaker()