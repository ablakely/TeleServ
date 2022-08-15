# TeleServ
Telegram to IRC bridge server

![screenshot](https://raw.githubusercontent.com/ablakely/TeleServ/main/doc/screenshot.png)

## What is TeleServ?
TeleServ is a telegram bot which links to an IRC network as an IRC server, this
allows Telegram users to appear as IRC users instead of relaying all messages
through a single IRC user. It also acts as a [bouncer](https://en.wikipedia.org/wiki/ZNC)
by allowing users to have a constant connection to IRC.

## What IRCds are supported?
TeleServ should work with any IRCd that uses TS6 for it's linking protocol, it has been tested on:
* InspIRCd 3.x (Protocol Version: 1205)

## Installing & Usage
1) Create a telegram bot \([tutorial](https://core.telegram.org/bots#6-botfather)\)
1) Create a link block on the IRC server you'll be linking to.
2) Edit `example.conf.json` and rename to `conf.json`
3) `pip install pyTelegramBotAPI`
4) `python TeleServ.py`

### Pastebin

![screenshot2](https://raw.githubusercontent.com/ablakely/TeleServ/main/doc/screenshot2.png)

TeleServ has the ability to automatically post long Telegram messages to pastebin to prevent
flooding an IRC channel, it will not do this for private messages between IRC and Telegram users. To enable this functionality you
will need to create a [Pastebin Account](https://pastebin.com/signup) for your TeleServ instance and provide the needed details in
your `conf.json` from the [API page](https://pastebin.com/doc_api).  Make sure to set `pastebinLongMessages` to `true`.  Messages
with a character count greater than or equal to `messageLength` will be posted to pastebin and a short preview.

#### Privacy Setting

| Value | Setting                                            |
|-------|----------------------------------------------------|
| 0     | Public                                             |
| 1     | Unlisted                                           |
| 2     | Private (Only acccount bot is using can view post) |


Due to limitations in the Pastebin API for free accounts, it is recommended to use the public setting
as non "PRO" accounts are only allowed to have 10 unlisted posts on the account.

## Commands

### Telegram


| Command  | Arguments       | Description                                                     |
|----------|-----------------|-----------------------------------------------------------------|
| /conn    | (none)          | Connects a telegram user to the IRC server                      |
| /setchan | \<chan\>        | (Group Admin/Owner) Sets IRC destination channel                |
| /me      | \<action\>      | Action command (* User slaps mIRC with a large trout)           |
| /notice  | \<msg\>         | Send a notice to an IRC user (or channel if no nick given)      |
| /pm      | \<nick\>        | Creates a private chat with an IRC user (DM with bot only)      |
| /nick    | (nick)          | Change your IRC nick (replies with current if nick not given)   |
| /names   | (none)          | List the users in the IRC channel                               |



### IRC

Usage: `/msg TeleServ <command>`

TeleServ will only respond to IRC operators.

| Command  | Arguments | Description                                                               |
|----------|-----------|---------------------------------------------------------------------------|
| help     | (none)                      | Sends the user a list of commands.                      |
| userlist | (none)                      | Sends the user the list of users being connected.       |
| whois    | \<nick or \@telegramuser\>  | Sends the user information about a bridge user.         |
-


_Copyright &copy; 2022 Aaron Blakely_

Support for this software is available on [IRC](https://webchat.ephasic.org/?join=ephasic) or [Telegram](https://t.me/+8NN0N6ez_B5iMzBh)
