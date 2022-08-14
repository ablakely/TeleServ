#!/usr/bin/python

# TeleServ - Telegram to IRC bridge server
#
# Copyright (c) 2022 Aaron Blakely
# Support: https://webchat.ephasic.org/?join=ephasic

import re
import os
from os.path import exists
from telebot import TeleBot,types,util,custom_filters
from lib.TSPastebinAPI import TSPastebinAPI
import socket
import ssl
import time
import threading
import json

motd = """
@@@@@@@@@@@@@@@@@@@@@@@(*#@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@    .@@@@@@@@@@@@@    ,@@@@@@@@@@@@@
@@@@@@@@@@   @@@@@@@@@@@@@@@@@@@@@@@@@   @@@@@@@@@
@@@@@@@@  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@  @@@@@@@
@@@@@  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@  @@@@    TeleServ (v1.0): Telegram Bridge Server
@@@@  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@  @@@
@@% @@@@@@@@@@@@@@@@@@@@@@@@@@@@     @@@@@@@@@@ @@
@@ @@@@@@@@@@@@@@@@@@@@@@@    @@    @@@@@@@@@@@@ @          Written by Aaron Blakely
@ *@@@@@@@@@@@@@@@@@    @@@@@  %@  @@@@@@@@@@@@@, 
@ @@@@@@@@@@@@    @@@@@@@@@  @@@  @@@@@@@@@@@@@@@ 
  @@@@@@    @@@@@@@@@@@@  @@@@@  @@@@@@@@@@@@@@@@ 
@ @@@@@@@@@   @@@@@@@@  @@@@@@  @@@@@@@@@@@@@@@@@       https://github.com/ablakely/TeleServ
@ .@@@@@@@@@@@@@     @@@@@@@@  @@@@@@@@@@@@@@@@@. 
@@ @@@@@@@@@@@@@@@@  @@@@@@@ ,@@@@@@@@@@@@@@@@@@ @
@@@ @@@@@@@@@@@@@@@@@ @@@@@ &@@@@@@@@@@@@@@@@@@ @@
@@@@  @@@@@@@@@@@@@@@@ @@@ @@@@@@@@@@@@@@@@@@  @@@
@@@@@  @@@@@@@@@@@@@@@@   @@@@@@@@@@@@@@@@@@ .@@@@
@@@@@@@@  @@@@@@@@@@@@@@&@@@@@@@@@@@@@@@@  @@@@@@@
@@@@@@@@@@,  @@@@@@@@@@@@@@@@@@@@@@@@@  .@@@@@@@@@
@@@@@@@@@@@@@@@    @@@@@@@@@@@@@    @@@@@@@@@@@@@@
"""


# Globals
lastID = 0
membID = 0
sock = {}
prevline = ""
initalBurstSent = False
logChannelJoined = False

remoteServer = {}
remoteServer["capab"] = {}
remoteServer["chans"] = {}
remoteServer["uids"]  = {}
remoteServer["opers"] = []

noticeBuf = ""
noticeBufMode = False

def readCfg(file):
    f = open(file)
    ret = json.load(f)
    f.close()

    if "enableRAW" not in ret:
        ret["enableRAW"] = False
    elif ret["enableRAW"] == True:
        print("[WARNING] The RAW command is enabled, this is not recommended for production use and should only be used by someone that knows how.")

    return ret

def loadLocalServerState():
    if exists("./bridgestates.json"):
        f = open("./bridgestates.json")
        ret = json.load(f)
        f.close()
    else:
        ret = {}
        ret["uids"] = {}
        ret["chanmap"] = {}

    return ret

def writeLocalServerState():
    f = open("./bridgestates.json", "w")
    json.dump(localServer, f, indent=2)
    f.close()


conf = readCfg("./conf.json")

if "PASTEBIN" in conf:
    pastebin = TSPastebinAPI(conf["PASTEBIN"])
else:
    pastebin = TSPastebinAPI({"pastebinLongMessages": False})

# This dict stores our Telegram config as well as client UID information,
# it will be saved to disk on SIGTERM or when a new user client is created.

localServer = loadLocalServerState()

bot = TeleBot(conf["API_KEY"])

class IsAdmin(custom_filters.SimpleCustomFilter):
    key = 'is_chat_admin'
    @staticmethod
    def check(message: types.Message):
        return bot.get_chat_member(message.chat.id, message.from_user.id).status in ['administrator', 'creator']

bot.add_custom_filter(IsAdmin())

def channelFromTGID(tgid):
    tgid = str(tgid)

    for chan in localServer["chanmap"]:
        if tgid == localServer["chanmap"][chan]:
            return chan

    return False

def userIDFromTGID(tgid):
    tgid = str(tgid)

    for uid in localServer["uids"]:
        if tgid == str(localServer["uids"][uid]["telegramid"]):
            return uid
    return False

def nickFromTGID(tgid):
    tgid = str(tgid)

    for uid in localServer["uids"]:
        if tgid == str(localServer["uids"][uid]["telegramid"]):
            return localServer["uids"][uid]["nick"]
    return False

def tgUserInChannel(tgid, chan):
    tgid = str(tgid)

    for uid in localServer["uids"]:
        if tgid == str(localServer["uids"][uid]["telegramid"]) and chan in localServer["uids"][uid]["chans"]:
            return True
    return False

def tgUserPMOpen(tgid):
    tgid = str(tgid)

    for uid in localServer["uids"]:
        if tgid == str(localServer["uids"][uid]["telegramid"]) and localServer["uids"][uid]["pm"] != "":
            return True
    return False

def setTGUserPM(tgid, uid):
    tgid = str(tgid)

    for i in localServer["uids"]:
        if tgid == str(localServer["uids"][i]["telegramid"]):
            localServer["uids"][i]["pm"] = uid

    writeLocalServerState()

def getTGUserPM(tgid):
    tgid = str(tgid)

    for uid in localServer["uids"]:
        if tgid == str(localServer["uids"][uid]["telegramid"]):
            return localServer["uids"][uid]["pm"]
    return False

def createTGUser(msg):
    global localServer, sock

    if msg.chat.type != "group": return
    if not msg.from_user.username:
        bot.reply_to(msg, "Error: You currently don't have a username set.")
        return False

    name = msg.from_user.first_name
    if msg.from_user.last_name:
        name += " " + msg.from_user.last_name

    if userIDFromTGID == False:
        bot.reply_to(msg, "Creating IRC client for {}".format(msg.from_user.username))
        sendIRCPrivMsg(sock, conf["IRC"]["nick"], conf["IRC"]["logchan"], "Creating client for {} in Telegram group: {}".format(msg.from_user.username, msg.chat.id))
   
        nick = msg.from_user.username[0:int(remoteServer["capab"]["NICKMAX"])]
        user = name.split(" ")[0][0:int(remoteServer["capab"]["IDENTMAX"])].lower()
        name = name[0:remoteServer["capab"]["MAXREAL"]]
        host = "t.me/{}".format(msg.from_user.username)[0:remoteServer["capab"]["MAXHOST"]]

        uid = addIRCUser(sock, user, nick, host, "+i", name)

        localServer["uids"][uid] = {}
        localServer["uids"][uid]["telegramuser"] = msg.from_user.username
        localServer["uids"][uid]["telegramid"]   = str(msg.from_user.id)
        localServer["uids"][uid]["name"]         = name
        localServer["uids"][uid]["nick"]         = nick
        localServer["uids"][uid]["user"]         = user
        localServer["uids"][uid]["host"]         = host
        localServer["uids"][uid]["pm"]           = ""
        localServer["uids"][uid]["chans"]        = []
    
    
    if tgUserInChannel(msg.from_user.id, channelFromTGID(msg.chat.id)) == False:
        joinIRCUser(sock, userIDFromTGID(msg.from_user.id), channelFromTGID(msg.chat.id), "v")
        localServer["uids"][userIDFromTGID(msg.from_user.id)]["chans"].append(channelFromTGID(msg.chat.id))

        bot.reply_to(msg, "Connecting you to {}".format(channelFromTGID(msg.chat.id)))
    else:
        bot.reply_to(msg, "You are already in this IRC channel.")

    writeLocalServerState()

def uidFromNick(nick):
    for uid in localServer["uids"]:
        if nick == localServer["uids"][uid]["nick"]:
            return uid

    for uid in remoteServer["uids"]:
        if nick == remoteServer["uids"][uid]["nick"]:
            return uid

    return False

def getUIDObj(uid):
    if uid in localServer["uids"]:
        return localServer["uids"][uid]

    if uid in remoteServer["uids"]:
        return remoteServer["uids"][uid]

    return False

def nickFromUID(tuid):
    if tuid in localServer["uids"]:
        return localServer["uids"][tuid]["nick"]

    if tuid in remoteServer["uids"]:
        return remoteServer["uids"][tuid]["nick"]

    return False

def uidFromTGUsername(username):
    username = username.replace("@", "")

    for uid in localServer["uids"]:
        if username == localServer["uids"][uid]["telegramuser"]:
            return uid
    return False

def uidToTGID(tuid):
    if tuid in localServer["uids"]:
        return localServer["uids"][tuid]["telegramid"]
    return False 

def updateLastMsg(tgid):
    for uid in localServer["uids"]:
        if tgid == localServer["uids"][uid]["telegramid"]:
            localServer["uids"][uid]["lastmsg"] = int(time.time())

def tgidFromNick(nick):
    for uid in localServer["uids"]:
        if nick == localServer["uids"][uid]["nick"]:
            return localServer["uids"][uid]["telegramid"]
    return False

def getLastMsgTime(tuid):
    if tuid in localServer["uids"]:
        return localServer["uids"][tuid]["lastmsg"]
    return False

def findIRCUserFromMSG(msg, lookupNick=True):
    if msg.chat.type == "group":
        to = channelFromTGID(msg.chat.id)
    elif msg.chat.type == "private":
        to = userIDFromTGID(msg.from_user.id)

        if lookupNick:
            to = nickFromUID(to)

    return to

#
# Utility functions
#
def log(msg):
    if conf["DEBUG"] == True: print(msg.strip())

#
# Telegram connection
#

@bot.message_handler(commands=['start','help'])
def startMsg(msg):
    global localServer, conf

    startMsg = """
    Hi\! I am TeleServ, an IRC bridge bot by [ablakely](https://github.com/ablakely)

I am currently linking this chat to: 
  `{chan}{server}`
    
*Group Commands:*
 /setchan `\<channel\>` \- \[Admin\] Set destination IRC channel for group
 /conn \- Creates an IRC client with your username \({user}\)
 /names \- List the IRC users in the channel

*DM Commands:*
 /pm `\<nick\>` \- Create a private chat with an IRC user

*Group and DM Commands:*
 /me `\<action\>` \- Action command
 /notice `\<msg\>` \- Send a notice
 /nick `\<nickname\>` \- Change your nickname on IRC
    
Any other messaged will be relayed to the IRC channel or user\."""

    chan = ""
    if channelFromTGID(msg.chat.id):
        chan = "\{} on ".format(channelFromTGID(msg.chat.id))
    else:
        chan = "\{} on ".format(findIRCUserFromMSG(msg))

    startMsg = startMsg.format(server=conf["IRC"]["server"].replace(".", "\."), user=msg.from_user.username, chan=chan)
    
    bot.reply_to(msg, startMsg, parse_mode="MarkdownV2")


@bot.message_handler(commands=['setchan'], is_chat_admin=True)
def setChan(msg):
    global sock, localServer

    if msg.chat.type != "group": return

    args = msg.text.split()
    if len(args) > 1:
        bot.reply_to(msg, "Setting IRC channel to {}".format(args[1]))

        sendIRCPrivMsg(sock, conf["IRC"]["nick"], conf["IRC"]["logchan"], "Setting IRC channel to {} for Telegram group: {}".format(args[1], msg.chat.id))

        localServer["chanmap"][args[1]] = str(msg.chat.id)
        writeLocalServerState()
    else:
        bot.reply_to(msg, "Usage: /setchan <IRC channel")

@bot.message_handler(commands=['conn'])
def conn(msg):
    createTGUser(msg)

@bot.message_handler(commands=['me'])
def tgSendIRCAction(msg):
    global sock, localServer

    if userIDFromTGID(msg.from_user.id) == False:
        bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
        return

    if msg.chat.type == "group" and tgUserPMOpen(msg.from_user.id) == False:
        bot.reply_to(msg, "You have not created a private message with a user")
        return

    to = findIRCUserFromMSG(msg)
    
    tmp = msg.text.split(" ")
    tmp.pop(0)

    tmp = " ".join(tmp)

    sendIRCPrivMsg(sock, msg.from_user.username, to, "\001ACTION {}\001".format(tmp))

@bot.message_handler(commands=['notice'])
def tgSendIRCNotice(msg):
    global sock, localServer

    if msg.chat.type != "group" and msg.chat.type != "private": return
    if userIDFromTGID(msg.from_user.id) == False:
        bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
        return

    if msg.chat.type == "group" and tgUserPMOpen(msg.from_user.id) == False:
        bot.reply_to(msg, "You have not created a private message with a user")
        return

    to = findIRCUserFromMSG(msg)

    args = msg.text.split()
    if len(args) > 1:
        sendIRCNotice(sock, msg.from_user.username, to, " ".join(args[1:]))
    else:
        bot.reply_to(msg, "Usage: /notice <msg> to send a notice to channel or /notice <who> <msg> to send a notice to a user.")

@bot.message_handler(commands=['pm'])
def tgSetPM(msg):
    global sock, localServer

    if msg.chat.type != "private":
        bot.reply_to(msg, "This command is to be used when directly messaging me.")
        return

    if userIDFromTGID(msg.from_user.id) == False:
        bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
        return

    args = msg.text.split()
    if len(args) > 1:
        for uid in remoteServer["uids"]:
            if args[1] == remoteServer["uids"][uid]["nick"]:
                bot.reply_to(msg, "I will now send your messages in this chat to {}".format(args[1]))
                setTGUserPM(msg.from_user.id, uid)
                return

        bot.reply_to(msg, "{} doesn't appear to be online.".format(args[1]))
        if tgUserPMOpen(msg.from_user.id) == True:
            setTGUserPM(msg.from_user.id, "")

@bot.message_handler(commands=['nick'])
def tgSetNick(msg):
    global sock, localServer

    if userIDFromTGID(msg.from_user.id) == False:
        bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
        return

    args = msg.text.split()
    if len(args) > 1:
        uid = userIDFromTGID(msg.from_user.id)

        if len(args[1]) > int(remoteServer["capab"]["NICKMAX"]):
            bot.reply_to(msg, "Error: Nicknames cannot be longer than {} characters.".format(remoteServer["capab"]["NICKMAX"]))
            return

        if re.match(r"[A-z_\-\[\]\\^{}|`][A-z0-9_\-\[\]\\^{}|`]*", args[1]):
            if uidFromNick(args[1]) == False:
                localServer["uids"][uid]["nick"] = args[1]
                ircOut(sock, ":{} NICK {} :{}".format(uid, args[1], int(time.time())))
                bot.reply_to(msg, "You are now known as {}".format(args[1]))

                writeLocalServerState()
            else:
                bot.reply_to(msg, "{} is in use.".format(args[1]))
        else:
            bot.reply_to(msg, "Nick contains invalid characters.")
    else:
        bot.reply_to(msg, "Your current nick is: {}".format(nickFromTGID(msg.from_user.id)))

@bot.message_handler(commands=['names'])
def tgNamesCmd(msg):
    if msg.chat.type != "group": return

    if channelFromTGID(msg.chat.id) == False:
        bot.reply_to(msg, "I am not linking this group to an IRC channel.")
        return

    chan = channelFromTGID(msg.chat.id)
    userlist = []

    for user in remoteServer["chans"][chan]["users"]:
        userlist.append(" {}".format(nickFromUID(user)))

    bot.reply_to(msg, "Users on {} ({} Users):\n{}".format(chan, len(userlist), " ".join(userlist)))

@bot.message_handler(func=lambda message: True, content_types=['text'])
def tgSendIRCMsg(msg):
    global sock, localServer

    if msg.chat.type == "group":
        if channelFromTGID(msg.chat.id) == False: return

        if userIDFromTGID(msg.from_user.id) == False:
            bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
            return

        nick = nickFromTGID(msg.from_user.id)
        chan = channelFromTGID(msg.chat.id)


        if pastebin.enabled() == True:
            if len(msg.text) >= pastebin.msglen():
                header = "# Automatically posted for {} in {} by TeleServ\n\n".format(nick, chan)
                paste = pastebin.paste(header + msg.text)

                log("PASTEBIN: Created paste {} for {} in {}".format(paste, msg.from_user.username, msg.chat.id))
                sendIRCPrivMsg(sock, conf["IRC"]["nick"], conf["IRC"]["logchan"], "PASTEBIN: Created paste {} for {} in {}".format(paste, msg.from_user.username, msg.chat.id))
                sendIRCPrivMsg(sock, nick, chan, "{}... Continued: {}".format(msg.text[0:150].replace("\n", ""), paste))
                bot.reply_to(msg, "Created unlisted paste {} and sent it to IRC".format(paste))
            else:
                msgs = msg.text.split("\n")
                for i in msgs:
                    sendIRCPrivMsg(sock, nick, chan, i)
        else:
            msgs = msg.text.split("\n")
            for i in msgs:
                sendIRCPrivMsg(sock, nick, chan, i)
    
        updateLastMsg(msg.from_user.id)
    elif msg.chat.type == "private":
        if userIDFromTGID(msg.from_user.id) == False:
            bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
            return

        if tgUserPMOpen(msg.from_user.id) == False:
            bot.reply_to(msg, "You have not created a private message with a user")
            return

        toUID = getTGUserPM(msg.from_user.id)
        to    = nickFromUID(toUID)

        bot.reply_to(msg, "Sending to {}".format(to))

        msgs = msg.text.split("\n")
        for i in msgs:
            sendIRCPrivMsg(sock, nickFromTGID(msg.from_user.id), toUID, i)
    
        updateLastMsg(msg.from_user.id)


@bot.chat_member_handler()
def tgChatMember(message: types.ChatMemberUpdated):
    old = message.old_chat_member
    new = message.new_chat_member

    if new.status == 'member':
        bot.send_message(message.chat.id, "Hello {name}!  This is an IRC relay group chat, you will now be connected to as {user}".format(name=new.user.first_name, user=new.user.username))

#
# Handle our connection to the IRC Server
#

def ircOut(sock, msg):
    msg = msg.replace("\n", "")
    msg = msg.replace("\r", "")

    maxlen = int(remoteServer["capab"]["MAXLINE"])-55 if "MAXLINE" in remoteServer["capab"] else 457

    if len(msg) > maxlen:
        cmdSearch = re.search(":(.*?) (.*?) (.*?) :(.*)", msg)
        if cmdSearch:
            matches = cmdSearch.groups()

            uid = matches[0]
            cmd = matches[1]
            target = matches[2]
            buf = matches[3]

            while buf != "":
                out = ":{} {} {} :{}\r\n".format(uid, cmd, target, buf[0:maxlen])
                log(out)
                sock.write(bytes(out, encoding='utf8'))
                buf = buf.replace(buf[0:maxlen], "", 1)
    else:
        log(msg[0:maxlen])
        sock.write(bytes("{}\r\n".format(msg[0:maxlen]), encoding='utf8'))

def addIRCUser(sock, user, nick, host, modes, real, isService=False):
    global lastID, localServer

    lastIDStr = str(lastID)
    calc = 6 - len(lastIDStr)
    ap = ""

    nick = nick[0:int(remoteServer["capab"]["NICKMAX"])]
    user = user[0:int(remoteServer["capab"]["IDENTMAX"])]
    real = real[0:int(remoteServer["capab"]["MAXREAL"])]
    host = host[0:int(remoteServer["capab"]["MAXHOST"])]

    while calc != 0:
        ap += "0"
        calc -= 1

    ruid = conf["IRC"]["sid"] + ap + lastIDStr

    if isService == True:
        modes += "o"

    ircOut(sock, ":{} UID {} {} {} {} {} {} 0.0.0.0 {} {} :{}".format(conf["IRC"]["sid"], ruid, int(time.time()), nick, host, host, user, time.time(), modes, real))

    if isService == True:
        ircOut(sock, ":{} OPERTYPE Service".format(ruid))

    lastID += 1
    return ruid

def joinIRCUser(sock, nick, chan, usermode):
    global remoteServer, localServer, membID

    if chan not in remoteServer["chans"]:
        remoteServer["chans"][chan] = {}
        remoteServer["chans"][chan]["ts"] = time.time()
        remoteServer["chans"][chan]["modes"] = "+nt"
        remoteServer["chans"][chan]["users"] = ["{},{}:{}".format(usermode, uidFromNick(nick), membID)]
        membID += 1

    remoteServer["chans"][chan]["users"].append(uidFromNick(nick))
    ircOut(sock, ":{} IJOIN {} {} {} :{}".format(uidFromNick(nick), chan, membID, remoteServer["chans"][chan]["ts"], usermode))
    membID += 1

def rejoinTGUsers(sock):
    global localServer

    for uid in localServer["uids"]:
        username = localServer["uids"][uid]["name"].split(" ")[0][0:int(remoteServer["capab"]["IDENTMAX"])].lower()
        nick     = localServer["uids"][uid]["nick"]
        host     = "t.me/{}".format(localServer["uids"][uid]["telegramuser"])[0:int(remoteServer["capab"]["MAXHOST"])]
        name     = localServer["uids"][uid]["name"]

        if nick == conf["IRC"]["nick"]:
            continue

        addIRCUser(sock, username, nick, host, "+i", name)

        for ichan in localServer["uids"][uid]["chans"]:
            joinIRCUser(sock, nick, ichan, "v")

def sendIRCAuth(sock):
    ircOut(sock, "CAPAB START 1205")
    ircOut(sock, "CAPAB END")
    ircOut(sock, "SERVER {} {} 0 {} :{}".format(conf["IRC"]["name"], conf["IRC"]["sendkey"], conf["IRC"]["sid"], conf["IRC"]["description"]))


def sendIRCBurst(sock):
    ircOut(sock, ":{} BURST".format(conf["IRC"]["sid"]))
    ircOut(sock, ":{} SINFO version: :1.0".format(conf["IRC"]["sid"]))
    ircOut(sock, ":{} SINFO fullversion :TeleServ 1.0 {} :[{}] {}".format(conf["IRC"]["sid"], conf["IRC"]["name"], conf["IRC"]["sid"], conf["IRC"]["network"]))
    uid = addIRCUser(sock, conf["IRC"]["nick"], conf["IRC"]["nick"], conf["IRC"]["name"], "+i", "Telegram IRC Bridge", isService=True)
    ircOut(sock, ":{} ENDBURST".format(conf["IRC"]["sid"]))

    localServer["uids"][uid] = {}
    localServer["uids"][uid]["nick"] = conf["IRC"]["nick"]
    localServer["uids"][uid]["name"] = "Telegram IRC Bridge"
    localServer["uids"][uid]["telegramuser"] = ""
    localServer["uids"][uid]["telegramid"] = 0
    localServer["uids"][uid]["lastmsg"] = 0
    localServer["uids"][uid]["chans"] = []

    writeLocalServerState()

def sendIRCPrivMsg(sock, nick, chan, msg):
    global localServer

    ircOut(sock, ":{} PRIVMSG {} :{}".format(uidFromNick(nick), chan, msg))

def sendIRCNotice(sock, nick, chan, msg):
    global localServer

    ircOut(sock, ":{} NOTICE {} :{}".format(nick, chan, msg))

def ircPrivMsgHandler(uid, target, msg, msgType="PRIVMSG"):
    global sock, remoteServer, localServer, noticeBuf, noticeBufMode

    nick = nickFromUID(uid)
    if nick == False and uid in remoteServer["uids"]:
        nick = remoteServer["uids"][uid]["nick"]
    else:
        nick = uid

    to = uidToTGID(target)
    toNick = nickFromUID(target)

    # strip mIRC formatting
    msg = re.sub(r"[\x02\x1F\x0F\x16]|\x03(\d\d?(,\d\d?)?)?", "", msg)
    
    if target == uidFromNick(conf["IRC"]["nick"]):
        tsuid = uidFromNick(conf["IRC"]["nick"])

        if uid not in remoteServer["opers"]:
            sendIRCNotice(sock, tsuid, nick, "Access denied.")
            return

        if msg == "help" or msg == "HELP":
            sendIRCNotice(sock, tsuid, nick, "***** \x02TeleServ Help\x02 *****")
            sendIRCNotice(sock, tsuid, nick, "\x02USERLIST\x02    List of Telegram users connected and their IRC nicks.")
            sendIRCNotice(sock, tsuid, nick, "\x02WHOIS\x02       Gives info about a Telegram user.")
            if conf["enableRAW"] == True:
                sendIRCNotice(sock, tsuid, nick, "\x02RAW\x02         Sends raw data to server socket. (Only use if you know how.)")
            sendIRCNotice(sock, tsuid, nick, "**** \x02End of Help\x02 *****")
        elif msg == "USERLIST" or msg == "userlist":
            sendIRCNotice(sock, tsuid, nick, "***** \x02Telegram Users\x02 *****")
            for k in localServer["uids"]:
                if localServer["uids"][k]["nick"] == conf["IRC"]["nick"]: continue
                sendIRCNotice(sock, tsuid, nick, "@{} is connected as {} in channels: {}".format(localServer["uids"][k]["telegramuser"], localServer["uids"][k]["nick"], " ".join(localServer["uids"][k]["chans"])))
        elif "RAW" in msg or "raw" in msg and conf["enableRAW"] == True:
            tmp = msg.split(" ")
            ircOut(sock, " ".join(tmp[1:]))
        elif "WHOIS" in msg or "whois" in msg:
            tmp = msg.split(" ")
            tuid = uidFromNick(tmp[1]) if tmp[1][0] != "@" else uidFromTGUsername(tmp[1])
            usr = getUIDObj(tuid)

            if usr != False:
                sendIRCNotice(sock, tsuid, nick, "Information for \x02{}\x02:".format(tmp[1]))
                sendIRCNotice(sock, tsuid, nick, "UID           : {}".format(tuid))
                sendIRCNotice(sock, tsuid, nick, "Nick          : {}".format(usr["nick"]))
                sendIRCNotice(sock, tsuid, nick, "Name          : {}".format(usr["name"]))
                sendIRCNotice(sock, tsuid, nick, "PM            : {}".format(nickFromUID(usr["pm"])))
                sendIRCNotice(sock, tsuid, nick, "Last Msg      : {}".format(time.strftime('%H:%M:%S %d-%m-%Y', time.localtime(usr["lastmsg"]))))
                sendIRCNotice(sock, tsuid, nick, "Telegram ID   : {}".format(usr["telegramid"]))
                sendIRCNotice(sock, tsuid, nick, "Telegram User : @{}".format(usr["telegramuser"]))
                sendIRCNotice(sock, tsuid, nick, "Channels      : {}".format(" ".join(usr["chans"])))
                sendIRCNotice(sock, tsuid, nick, "\x02*** End of WHOIS ***\x02")
            else:
                sendIRCNotice(sock, tsuid, nick, "Error: {} is not online.".format(tmp[1]))
        else:
            sendIRCNotice(sock, tsuid, nick, "Invalid command. Use \x02/msg {} help\x02 for a command listing.".format(conf["IRC"]["nick"]))
    elif target in localServer["uids"]:
        senderNick = nickFromUID(uid)
        to = tgidFromNick(toNick)
        nick = nickFromUID(nick)

        if to == False or tgUserPMOpen(to) == False:
            sendIRCNotice(sock, target, nick, "Error: {} has not created a private message with you.  Ask them to do /pm {}".format(toNick, nick))
            return

        if re.search(r"ACTION (.*)", msg):
            msg = re.sub("ACTION ", "", msg)
            bot.send_message(to, "* {}{}".format(senderNick, msg))
        else:
            if msgType == "PRIVMSG":
                bot.send_message(to, "<{}> {}".format(senderNick, msg))
            elif msgType == "NOTICE":
                if re.search(r"\*\*\*\*\* (.*?) Help \*\*\*\*\*", msg):
                    noticeBufMode = True
                if re.search(r"\*\*\*\*\* End of Help \*\*\*\*\*", msg):
                    noticeBufMode = False
                    bot.send_message(to, noticeBuf)
                    noticeBuf = ""
                
                if noticeBufMode == True:
                    noticeBuf += "-{}- {}\n".format(senderNick, msg)
                else:
                    bot.send_message(to, "-{}- {}".format(senderNick, msg))        
    elif target in localServer["chanmap"]:
        to = localServer["chanmap"][target]
        nick = nickFromUID(nick)

        if re.search(r"ACTION (.*)", msg):
            msg = re.sub("ACTION ", "", msg)
            bot.send_message(to, "* {}{}".format(nick, msg))
        else:
            if msgType == "PRIVMSG":
                bot.send_message(to, "<{}> {}".format(nick, msg))
            elif msgType == "NOTICE":
                bot.send_message(to, "-{}- {}".format(nick, msg))    


def handleSocket(rawdata, sock):
    global initalBurstSent, prevline, logChannelJoined

    for data in rawdata.split("\n"):
        if data == "": continue

        capabSearch = re.search(r"^CAPAB (.*?) (.*)$", data)
        if capabSearch:
            matches = capabSearch.groups()
            args = matches[1]

            if args[0] == ":":
                args = args.replace(":", "", 1)

            if matches[0] == "START":
                if int(args) < 1205:
                    print("Error: InspIRCd linking protocol version {} is not supported.".format(args))
                    exit()

                remoteServer["capab"]["version"] = args
            elif matches[0] == "CAPABILITIES":
                for capability in args.split(" "):
                    capab = re.search(r"(.*?)=(.*)", capability)
                    if capab:
                        capab = capab.groups()
                        remoteServer["capab"][capab[0]] = capab[1]
            else:
                remoteServer["capab"][matches[0]] = args.split(" ")

            continue

        if data[0] != ":":
            data = prevline + data +"\n"

        log("IRC RAW: {}".format(data))

        if re.search(r":(.*)", data):
            matches = re.search(r"SERVER (.*?) (.*?) 0 (.*?) :(.*)", data)
            if matches:
                matches = matches.groups()
                remoteServer["hostname"] = matches[0]
                remoteServer["recvkey"] = matches[1]
                remoteServer["SID"] = matches[2]
                remoteServer["description"] = matches[3]

                if initalBurstSent == False:
                    sendIRCBurst(sock)
                    initalBurstSent = True

            matches = re.search(r":(.*?) FJOIN (.*?) (\d+) (.*?) :(.*)", data)
            if matches:
                matches = matches.groups()
                remoteServer["chans"][matches[1]] = {}
                remoteServer["chans"][matches[1]]["ts"] = matches[2]
                remoteServer["chans"][matches[1]]["modes"] = matches[3]
                remoteServer["chans"][matches[1]]["users"] = []

                for user in matches[4].split(" "):
                    usermatch = re.search(r"(.*?),(.*)", user)
                    if usermatch:
                        usermatch = usermatch.groups()
                        useruid = usermatch[1].split(":")[0]
                        print(useruid)
                        remoteServer["chans"][matches[1]]["users"].append(useruid)

                        if useruid in remoteServer["uids"]:
                            remoteServer["uids"][useruid]["chans"].append(matches[1])

            matches = re.search(r":(.*?) UID (.*?) (\d+) (.*?) (.*?) (.*?) (.*?) (.*?) (\d+) (.*?) :(.*)", data)
            if matches:
                matches = matches.groups()
                remoteServer["uids"][matches[1]] = {}
                remoteServer["uids"][matches[1]]["ts"] = matches[2]
                remoteServer["uids"][matches[1]]["nick"] = matches[3]
                remoteServer["uids"][matches[1]]["ip"] = matches[4]
                remoteServer["uids"][matches[1]]["host"] = matches[5]
                remoteServer["uids"][matches[1]]["user"] = matches[6]
                remoteServer["uids"][matches[1]]["ts1"] = matches[8]
                remoteServer["uids"][matches[1]]["modes"] = matches[9]
                remoteServer["uids"][matches[1]]["name"] = matches[10]
                remoteServer["uids"][matches[1]]["chans"] = []

            matches = re.search(r":(.*?) PRIVMSG (.*?) :(.*)", data)
            if matches:
                matches = matches.groups()

                if re.search(r"\x01VERSION\x01", matches[2]):
                    ircOut(sock, ":{} NOTICE {} :VERSION TeleServ v1.0: Telegram to IRC bridge (https://github.com/ablakely/TeleServ) by Aaron Blakely".format(matches[1], matches[0]))
                else:
                    ircPrivMsgHandler(matches[0], matches[1], matches[2])

            matches = re.search(r":(.*?) NOTICE (.*?) :(.*)", data)
            if matches:
                matches = matches.groups()

                ircPrivMsgHandler(matches[0], matches[1], matches[2], msgType="NOTICE")

            matches = re.search(r":(.*?) IDLE (.*)", data)
            if matches:
                matches = matches.groups()

                if uidFromNick(conf["IRC"]["nick"]) == matches[1]:
                    ircOut(sock, ":{} IDLE {} :0".format(matches[1], matches[0]))
                    return

                if getLastMsgTime(matches[1]) != False:
                    calc = int(time.time()) - getLastMsgTime(matches[1])
                    ircOut(sock, ":{} IDLE {} :{}".format(matches[1], matches[0], calc))
                else:
                    ircOut(sock, ":{} IDLE {} :0".format(matches[1], matches[0]))

            matches = re.search(r":(.*?) MOTD :(.*)", data)
            if matches:
                matches = matches.groups()

                motdSplit = motd.split("\n")
                ircOut(sock, "NUM {} {} 375 :- {} Message of the day -".format(conf["IRC"]["sid"], matches[0], conf["IRC"]["name"]))
                for line in motdSplit:
                    ircOut(sock, "NUM {} {} 372 :- {}".format(conf["IRC"]["sid"], matches[0], line))
                ircOut(sock, "NUM {} {} 376 :End of Message of the Day.".format(conf["IRC"]["sid"], matches[0]))

            matches = re.search(r":(.*?) NICK (.*?) (.*)", data)
            if matches:
                matches = matches.groups()
                
                oldnick = remoteServer["uids"][matches[0]]["nick"]
                remoteServer["uids"][matches[0]]["nick"] = matches[1]

                sent = []

                for chan in remoteServer["uids"][matches[0]]["chans"]:
                    if chan in localServer["chanmap"]:
                        to = localServer["chanmap"][chan]

                        if to not in sent:
                            bot.send_message(to, "{} is now known as {}".format(oldnick, matches[1]))
                            sent.append(to)

            matches = re.search(r":(.*?) OPERTYPE :(.*)", data)
            if matches:
                matches = matches.groups()
                remoteServer["opers"].append(matches[0])

            matches = re.search(r":(.*?) PING (.*)", data)
            if matches:
                matches = matches.groups()
                ircOut(sock, ":{} PONG :{}".format(conf["IRC"]["sid"], matches[0]))

                if logChannelJoined == False:
                    logChannelJoined = True
                    joinIRCUser(sock, conf["IRC"]["nick"], conf["IRC"]["logchan"], "o")
                    rejoinTGUsers(sock)

            matches = re.search(r":(.*?) PART (.*)", data)
            if matches:
                matches = matches.groups()
                args = matches[1].split(" ")
                
                if args[0] in localServer["chanmap"]:
                    to = localServer["chanmap"][args[0]]

                    if len(args) > 1:
                        bot.send_message(to, "{} has left {} (Reason: {})".format(remoteServer["uids"][matches[0]]["nick"], args[0], " ".join(args[1:]).replace(":", "")))
                    else:
                        bot.send_message(to, "{} has left {}".format(remoteServer["uids"][matches[0]]["nick"], args[0]))

                remoteServer["chans"][args[0]]["users"].remove(matches[0])
                remoteServer["uids"][matches[0]]["chans"].remove(args[0])

            matches = re.search(r":(.*?) IJOIN (.*)", data)
            if matches:
                matches = matches.groups()
                args = matches[1].split(" ")
                
                if args[0] in localServer["chanmap"]:
                    to = localServer["chanmap"][args[0]]

                    bot.send_message(to, "{} ({}@{}) has joined {}".format(
                        remoteServer["uids"][matches[0]]["nick"],
                        remoteServer["uids"][matches[0]]["user"],
                        remoteServer["uids"][matches[0]]["host"],
                        args[0]))

                remoteServer["uids"][matches[0]]["chans"].append(args[0])
                remoteServer["chans"][args[0]]["users"].append(matches[0])

            matches = re.search(r":(.*?) QUIT (.*)", data)
            if matches:
                matches = matches.groups()

                for chan in remoteServer["uids"][matches[0]]["chans"]:
                    if chan in localServer["chanmap"]:
                        to = localServer["chanmap"][chan]

                        if matches[1]:
                            bot.send_message(to, "{} has quit (Reason: {})".format(remoteServer["uids"][matches[0]]["nick"], matches[1].replace(":", "", 1)))
                        else:
                            bot.send_message(to, "{} has quit".format(remoteServer["uids"][matches[0]]["nick"]))
                    
                    remoteServer["uids"][matches[0]]["chans"].remove(chan)
                    remoteServer["chans"][chan]["users"].remove(matches[0])


        prevline = data


def tgPoll():
    bot.infinity_polling(allowed_updates=util.update_types)

def main():
    global sock, conf

    print("Creating telegram polling thread.")
    threading.Thread(target=tgPoll, name='bot_infinity_polling', daemon=True).start()

    print("Creating SSL connection to {}".format(conf["IRC"]["server"]))
    rawsock = socket.socket(socket.AF_INET)
    context = ssl._create_unverified_context()
    sock = context.wrap_socket(rawsock, server_hostname=conf["IRC"]["server"])

    try:
        sock.connect((conf["IRC"]["server"], conf["IRC"]["port"]))
        sendIRCAuth(sock)

        print("")
        while True:
            data = sock.recv().decode("utf-8", "ignore")
            if not data: break

            handleSocket(data, sock)

    finally:
        print("\nWriting bridgestates.json")
        writeLocalServerState()

        print("Error: IRC server closed the connection, exiting.")
        sock.close()

if __name__ == '__main__':
    main()