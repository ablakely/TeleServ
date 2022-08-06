# TeleServ
Telegram to IRC (TS6) bridge server

## What is TeleServ?
TeleServ is a telegram bot which links to an IRC network as an IRC server, this
allows Telegram users to appear as IRC users instead of relaying all messages
through a single IRC user.

## What IRCds are supported?
TeleServ should work with any IRCd that uses TS6 for it's linking protocl, it has been tested on:
* InspIRCd 3.x


## Commands

### Telegram Group

-------------------------------------------------------------------------------
| Command | Arguments | Description                                           |
|---------|-----------|-------------------------------------------------------|
| conn    | (none)    | Connects a telegram user to the IRC server            |
| setchan | \<chan\>    | (Group Admin/Owner) Sets IRC destination channel      |
| me      | \<action\>  | Action command (* User slaps mIRC with a large trout) |
-------------------------------------------------------------------------------

---
Copyright &copy; 2022 Aaron Blakely
Support for this software is available on [IRC](https://webchat.ephasic.org/?join=ephasic) or [Telegram](https://t.me/ephasic)