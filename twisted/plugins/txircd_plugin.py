from twisted.application.service import IServiceMaker
from twisted.plugin import IPlugin
from twisted.python import usage
from zope.interface import implements

from txircd.ircd import IRCd

class Options(usage.Options):
    # If we ever start having options, don't forget to put them here
    pass

class IRCdServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "txircd"
    description = "Twisted IRC Server"
    options = Options
    
    def makeService(self, options):
        return IRCd()

txircd = IRCdServiceMaker()