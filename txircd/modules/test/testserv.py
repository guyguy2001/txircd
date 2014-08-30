from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData
from zope.interface import implements

from service import Service

class TestServ(Service):
    implements(IPlugin, IModuleData)

    name = "TestServ"
    help = "A test service."
    user_cmd_aliases = {
        "TEST": (20, "TEST"),
        "TSERV": (20, None),
    }

    def serviceCommands(self):
        return {
            "TEST": (self.handleTest, False, "a test command",
                "This command does nothing but send a notice echoing the input params, "
                "and is intended for testing the functionality of a very basic service."),
        }

    def handleTest(self, user, params):
        self.tellUser(user, " ".join(params))

testServ = TestServ()
