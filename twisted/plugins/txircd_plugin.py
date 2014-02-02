from twisted.application.service import IServiceMaker
from twisted.plugin import IPlugin
from twisted.python import usage
from zope.interface import implements

class Options(usage.Options):
    # If we ever start having options, don't forget to put them here
    pass

class IRCdServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "txircd"
    description = "Twisted IRC Server"
    options = Options
    
    def makeService(self, options):
        # Return a service from here once I make one
        pass

txircd = IRCdServiceMaker()