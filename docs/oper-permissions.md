This document describes all of the oper permissions used by the modules of
txircd. These permissions are important, as an oper with no permissions in
their oper block is effectively a normal user with no extra rights. This
document is divided in two sections: core permissions, that come with the core
modules and extra permissions, that come with the extra modules that can be
loaded.

Core Permissions
================

Permission            | Description
----------------------|------------------------------------
command-connect       | Allows the use of the CONNECT command to connect a remote server to the network.
command-die           | Allows the use of the DIE command to shut down the server.
command-eline         | Allows the use of the ELINE command to globally except a user from bans.
command-gline         | Allows the use of the GLINE command to globally ban a user.
command-kill          | Allows the use of the KILL command to disconnect a user.
command-kline         | Allows the use of the KLINE command to locally ban a user.
command-loadmodule    | Allows the use of the LOADMODULE command to load a module on the server.
command-qline         | Allows the use of the QLINE command to globally ban a nickname.
command-rehash        | Allows the use of the REHASH command to rehash the server's configuration.
command-reloadmodule  | Allows the use of the RELOADMODULE command to reload a module on the server.
command-restart       | Allows the use of the RESTART command to restart the server.
command-squit         | Allows the use of the SQUIT command to disconnect a server from the network.
command-unloadmodule  | Allows the use of the UNLOADMODULE command to unload a module on the server. Note that core modules cannot be unloaded.
command-wallops       | Allows the use of the WALLOPS command to send a WALLOPS message.
command-zline         | Allows the use of the ZLINE command to globally ban an IP address.
info-elines           | Allows an oper to view the elines STATS type.
info-klines           | Allows an oper to view the klines STATS type.
info-glines           | Allows an oper to view the glines STATS type.
info-qlines           | Allows an oper to view the qlines STATS type.
info-zlines           | Allows an oper to view the zlines STATS type.
override-invisible    | Allows an oper to view users in /NAMES, /WHO, and other lists even if they wouldn't be able to due to the user mode +i being set.
whois-host            | Allows an oper to see the real host and IP address of any user.


Extra Permissions
=================

Permission                | Module                    | Description
--------------------------|---------------------------|------------------------------------
channel-denied            | DenyChannels              | Allows an oper to join a channel that is not allowed by the module configuration.
command-censor            | Censor                    | Allows the use of the CENSOR command to disallow and replace a given word.
command-globops           | Globops                   | Allows the use of the GLOBOPS command to send a notice to opers who have permission to view them.
command-gloadmodule       | GlobalLoad                | Allows the use of the GLOADMODULE command to load a module on all servers on the network.
command-greloadmodule     | GlobalLoad                | Allows the use of the GRELOADMODULE command to reload a module on all servers on the network.
command-gunloadmodule     | GlobalLoad                | Allows the use of the GUNLOADMODULE command to unload a module on all servers on the network.
command-sajoin            | SajoinCommand             | Allows the use of the SAJOIN command to force join a user to a channel.
command-sakick            | SakickCommand             | Allows the use of the SAKICK command to force kick a user from a channel.
command-samode            | SamodeCommand             | Allows the use of the SAMODE command to change a mode on any user or channel.
command-sanick            | SanickCommand             | Allows the use of the SANICK command to change the nickname of any user.
command-sapart            | SapartCommand             | Allows the use of the SAPART command to force part a user from a channel.
command-satopic           | SatopicCommand            | Allows the use of the SATOPIC command to force change the topic of any channel.
command-shun              | Shun                      | Allows the use of the SHUN command to ban a user from sending most commands.
info-onlineopers          | StatsOnlineOpers          | Allows an oper to view the onlineopers STATS type.
info-ports                | StatsPorts                | Allows an oper to view the ports STATS type.
info-shuns                | Shun                      | Allows an oper to view the shuns STATS type.
info-uptime               | StatsUptime               | Allows an oper to view the uptime STATS type.
servernotice-connect      | ServerNoticeConnect       | Allows an oper to set usermode +s on themselves and grants permission for local connect notices.
servernotice-oper         | ServerNoticeOper          | Allows an oper to set usermode +s on themselves and grants permission for oper notices.
servernotice-quit         | ServerNoticeQuit          | Allows an oper to set usermode +s on themselves and grants permission for local quit notices.
servernotice-remoteconnect| ServerNoticeRemoteConnect | Allows an oper to set usermode +s on themselves and grants permission for remote connect notices.
servernotice-remotequit   | ServerNoticeRemoteQuit    | Allows an oper to set usermode +s on themselves and grants permission for remote quit notices.
view-globops              | Globops                   | Allows an oper to see GLOBOPS messages.