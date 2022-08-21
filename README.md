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

## Installing
1) Create a telegram bot \([tutorial](https://core.telegram.org/bots#6-botfather)\)
2) Create a link block on the IRC server you'll be linking to.
3) Edit `example.conf.json` and rename to `conf.json`
4) `pip install pyTelegramBotAPI imgurpython`
5) `python TeleServ.py`

## Usage
1) Create a telegram group and add the bot to it.
2) In the group use the `/setchan` command to link the group to an IRC channel.
3) Use `/conn` to connect your user the IRC channel.

## Commands

TeleServ provides commands for both Telegram users and IRC operators.

### Telegram


| Command      | Arguments       | Description                                                       |
|--------------|-----------------|-------------------------------------------------------------------|
| /help        | (none)          | Command list                                                      |
| /conn        | (none)          | Connects a telegram user to the IRC server                        |
| /setchan     | \<chan\>        | (Group Admin/Owner) Sets IRC destination channel                  |
| /me          | \<action\>      | Action command (* User slaps mIRC with a large trout)             |
| /notice      | \<msg\>         | Send a notice to an IRC user (or channel if no nick given)        |
| /pm          | \<nick\>        | Creates a private chat with an IRC user (private only)            |
| /nick        | (nick)          | Change your IRC nick (replies with current if nick not given)     |
| /names       | (none)          | List the users in the IRC channel                                 |
| /whois       | \<nick\>        | Lookup details about an IRC user                                  |
| /photos      | (none)          | Lists the imgur albums the bot has created for you (private only) |
| /deletealbum | \<album id\>    | Deletes an album the bot has created (private only)               |


### IRC

Usage: `/msg TeleServ <command>`

TeleServ will only respond to IRC operators.

| Command  | Arguments | Description                                                               |
|----------|-----------|---------------------------------------------------------------------------|
| help     | (none)                      | Sends the user a list of commands.                      |
| userlist | (none)                      | Sends the user the list of users being connected.       |
| whois    | \<nick or \@telegramuser\>  | Sends the user information about a bridge user.         |

---

## Imgur

![screenshot3](https://raw.githubusercontent.com/ablakely/TeleServ/main/doc/screenshot3.png)

TeleServ has the ability to upload images sent to Telegram chats it is in to Imgur and forward the link to to uploaded images as an imgur album to IRC.  To set this up you will need to:

1) Create an Imgur account for your TeleServ instance.
2) Create an Imgur [API key](https://api.imgur.com/oauth2/addclient) with the "Anonymous usage" type
3) Modify your conf.json with the ID and Secret keys that you generated, make sure to set `enabled` to `true`.
4) TeleServ will message the channel you have set for loging with an authorization link, allow it access to the account you made.
4) Set the pin imgur provides to you with `/msg TeleServ imgurpin <pin>` on IRC


## Pastebin

![screenshot2](https://raw.githubusercontent.com/ablakely/TeleServ/main/doc/screenshot2.png)

TeleServ has the ability to automatically post long Telegram messages to pastebin to prevent
flooding an IRC channel, it will not do this for private messages between IRC and Telegram users. To enable this functionality you
will need to create a [Pastebin Account](https://pastebin.com/signup) for your TeleServ instance and provide the needed details in
your `conf.json` from the [API page](https://pastebin.com/doc_api).  Make sure to set `pastebinLongMessages` to `true`.  Messages
with a character count greater than or equal to `messageLength` will be posted to pastebin and a short preview.

### Expiration Time

Pastebin does not support any other value for post expiration than the ones listed here.

| Value | Expiration Setting |
|-------|--------------------|
| N     | Never              |
| 10M   | 10 Minutes         |
| 1H    | 1 Hour             |
| 1D    | 1 Day              |
| 1W    | 1 Week             |
| 2W    | 2 Weeks            |
| 1M    | 1 Month            |
| 6M    | 6 Months           |
| 1Y    | 1 Year             |

### Privacy

Due to limitations in the Pastebin API for free accounts, it is recommended to use the public setting
as non [PRO](https://pastebin.com/pro) accounts are only allowed to have 10 unlisted posts on the account.

| Value | Privacy Setting                                    |
|-------|----------------------------------------------------|
| 0     | Public                                             |
| 1     | Unlisted                                           |
| 2     | Private (Only acccount bot is using can view post) |

---
_Copyright &copy; 2022 Aaron Blakely_

Support for this software is available on [IRC](https://webchat.ephasic.org/?join=ephasic) or [Telegram](https://t.me/+8NN0N6ez_B5iMzBh)
