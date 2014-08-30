from txircd.module_interface import Command, ICommand, ModuleData
from txircd.user import LocalUser
from txircd.utils import splitMessage
from zope.interface import implements


class Service(ModuleData):
    """A service is a specific kind of module, with some pre-made stuff to assist in
    creating a pseudo-user that can do useful things in response to commands."""

    @property
    def nick(self):
        """The name to use for the service user. Defaults to the module"s name."""
        return self.name

    # Long description of what this service does and how to use it.
    # Should not go into detail of particular commands (this info is generated from per-command help)
    help = ""

    # An optional dict mapping user commands to (priority, service command)
    # For example, {"PASS": (20, "LOGIN")} will alias the irc command PASS
    # to the service command "LOGIN" with the same params.
    # If you give None instead of a service command, it will instead expect the command as an arg,
    # eg. {"MYSERV": (20, None)} wil alias the command MYSERV to send a message to your service.
    user_cmd_aliases = {}

    def serviceCommands(self):
        """Should return a dict mapping commands to tuple (handler, admin_only, summary, help).
        Commands MUST be upper case.
        handler: The function to be called in response to this command.
        admin_only: Flag. When true, only admins for this service can use this command.
        summary: A one-line summary for what the command does.
                 Set this to None to make the command not show up in the command list.
        help: Full-length usage help for the command.
        """
        return {}

    def getIdentityInfo(self):
        """Optional method that should return identity info for the service user
        as a dict with keys "host", "ident" and "gecos".
        """
        return {}

    def _serviceCommands(self):
        """For internal use. Gets custom serviceCommands and then adds in default ones."""
        commands = {
            "HELP": (self.handleHelp, False, "Get help on specific commands",
                     ("This command can be run with no arguments to get a help summary and command list, "
                     "or you can give it specific commands to get extra info on them - for example, "
                     "\x02/msg {} HELP HELP\x02 will print this message.").format(self.nick)
                    ),
        }
        commands.update(self.serviceCommands())
        return commands

    def hookIRCd(self, ircd):
        self.ircd = ircd

    def load(self):
        self.user = LocalUser(self.ircd, "127.0.0.1")
        self.user.setSendMsgFunc(self.handleMessage)
        self.user.changeNick(self.nick)
        info = self.getIdentityInfo()
        self.user.changeIdent(info.get("ident", self.nick))
        self.user.changeGecos(info.get("gecos", self.nick))
        self.user.changeHost(info.get("host", self.ircd.name))
        self.user.register("NICK")

    def actions(self):
        return [("localnickcollision", 20, self.handleNickCollision)]

    def handleNickCollision(self, localUser, remoteUser, fromServer):
        if localUser == self.user:
            remoteUser.changeNick(remoteUser.uuid)
            return False

    def handleMessage(self, user, command, *params, **kw):
        """Handle any messages directly addressed to us."""
        if command != "PRIVMSG":
            return
        if "to" in kw:
            # TODO is this really the best way to determine this?
            return # message was a channel message
        if "sourceuser" not in kw:
            return # we don't know who it's from?
        if not params:
            return
        text = params[0]
        if text.startswith(":"):
            text = text[1:] # strip leading :
        service_params = filter(None, text.split())
        if not service_params:
            return
        command = service_params.pop(0)
        self.handleCommand(kw["sourceuser"], command, service_params)

    def userCommands(self):
        class AliasCommand(Command):
            implements(ICommand)
            def __init__(self, service, service_cmd):
                self.service = service
                self.service_cmd = service_cmd
            def parseParams(self, source, params, prefix, tags):
                if self.service_cmd:
                    command = self.service_cmd
                else:
                    if not params:
                        return None
                    command, params = params[0], params[1:]
                return {"command": command, "params": params}
            def execute(self, source, data):
                self.service.handleCommand(source, data["command"], data["params"])
        return [(user_cmd, priority, AliasCommand(self, service_cmd))
                for user_cmd, (priority, service_cmd) in self.user_cmd_aliases.items()]

    def handleCommand(self, user, command, params):
        command = command.upper()
        commands = self._serviceCommands()
        if command in commands:
            handler, admin_only, summary, long_help = commands[command]
            if not admin_only or self.isAdmin(user):
                handler(user, params)
                return
        self.tellUser(user, "Unknown command \x02{}\x02. Use \x1f/msg {} HELP\x1f for help.".format(command, self.name))

    def handleHelp(self, user, params):
        if not params:
            self.tellUser(user, self.help)
            for command, (handler, admin_only, summary, long_help) in sorted(self._serviceCommands().items()):
                if admin_only and not self.isAdmin(user):
                    continue
                if summary is None:
                    continue
                self.tellUser(user, "\x02{}\x02: {}".format(command, summary), split=False)
            self.tellUser(user, "*** End of help")
            return
        command = params[0].upper()
        if command in self._serviceCommands():
            handler, admin_only, summary, long_help = self._serviceCommands()[command]
            if not admin_only or self.isAdmin(user):
                self.tellUser(user, "*** Help for \x02{}\x02:".format(command))
                self.tellUser(user, long_help)
                self.tellUser(user, "*** End of help for \x02{}\x02".format(command))
                return
        self.tellUser(user, "No help available for \x02{}\x02".format(command))

    def isAdmin(self, user):
        return self.ircd.runActionUntilValue("userhasoperpermission", user, "service-admin-{}".format(self.name))

    def tellUser(self, user, message, split=True):
        if user.uuid not in self.ircd.users:
            return # user has disconnected
        chunks = splitMessage(message, 80) if split else [message]
        for chunk in chunks:
            user.sendMessage("NOTICE", ":{}".format(chunk), sourceuser=self.user)
