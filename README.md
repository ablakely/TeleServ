# TeleServ
Telegram to IRC (TS6) bridge server

## What is TeleServ?
TeleServ is a telegram bot which links to an IRC network as an IRC server, this
allows Telegram users to appear as IRC users instead of relaying all messages
through a single IRC user.

## What IRCds are supported?
TeleServ should work with any IRCd that uses TS6 for it's linking protocl, it has been tested on:
* InspIRCd 3.x

## Installing & Usage
1) Create a telegram bot \([tutorial](https://core.telegram.org/bots#6-botfather)\)
1) Create a link block on the IRC server you'll be linking to.
2) Edit `example.conf.json` and rename to `conf.json`
3) `pip install pyTelegramBotAPI`
4) `python TeleServ.py`


## Commands

### Telegram

-----------------------------------------------------------------------------------------------
| Command  | Arguments       | Description                                                     |
|----------|-----------------|-----------------------------------------------------------------|
| /conn    | (none)          | Connects a telegram user to the IRC server                      |
| /setchan | \<chan\>        | (Group Admin/Owner) Sets IRC destination channel                |
| /me      | \<action\>      | Action command (* User slaps mIRC with a large trout)           |
| /notice  | \<msg\>         | Send a notice to an IRC user (or channel if no nick given)      |
| /pm      | \<nick\>        | Creates a private chat with an IRC user (DM with bot only)      |
| /nick    | (nick)          | Change your IRC nick (replies with current if nick not given)   |
| /names   | (none)          | List the users in the IRC channel                               |
------------------------------------------------------------------------------------------------


### IRC

Usage: `/msg TeleServ <command>`

TeleServ will only respond to IRC operators.

---------------------------------------------------------------------------------------------------
| Command  | Arguments | Description                                                               |
|----------|-----------|---------------------------------------------------------------------------|
| help     | (none)                      | Sends the user a list of commands.                      |
| userlist | (none)                      | Sends the user the list of users being connected.       |
| whois    | \<nick or \@telegramuser\>  | Sends the user information about a bridge user.         |
----------------------------------------------------------------------------------------------------


Copyright &copy; 2022 Aaron Blakely

Support for this software is available on [IRC](https://webchat.ephasic.org/?join=ephasic) or [Telegram](https://t.me/+8NN0N6ez_B5iMzBh)
