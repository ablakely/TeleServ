#!/usr/bin/python

# TeleServ - Telegram to IRC(TS6) bridge server
#
# Copyright (c) 2022 Aaron Blakely
# Support: https://t.me/ephasic

import re
import os
from os.path import exists
from telebot import TeleBot,types,util,custom_filters
from pprint import pprint
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

def readCfg(file):
    f = open(file)
    ret = json.load(f)
    f.close()

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
        ret["users"] = []
        ret["names"] = {}
        ret["chans"] = {}
        ret["lastmsg"] = {}
        ret["telegramids"] = {}
        ret["pms"] = {}
    
    return ret

def writeLocalServerState():
    f = open("./bridgestates.json", "w")
    json.dump(localServer, f)
    f.close()


conf = readCfg("./conf.json")

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

def findIRCUserFromMSG(msg, lookupUID=True):
    if msg.chat.type == "group":
        if str(msg.chat.id) not in localServer["chanmap"].keys(): return

        to = localServer["chanmap"][str(msg.chat.id)]
    elif msg.chat.type == "private":
        if str(msg.from_user.id) in localServer["pms"]:
            to = localServer["pms"][str(msg.from_user.id)]

            if lookupUID:
                for uid in remoteServer["uids"]:
                    if remoteServer["uids"][uid]["nick"] == to:
                        to = uid

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

*DM Commands:*
 /pm `\<nick\>` \- Create a private chat with an IRC user

*Group and DM Commands:*
 /me `\<action\>` \- Action command
 /notice `\<msg\>` \- Send a notice to a user \(or channel if no nick given\)
    
Any other messaged will be relayed to the IRC channel or user\."""

    chan = ""
    if str(msg.chat.id) in localServer["chanmap"]:
        chan = "\{} on ".format(localServer["chanmap"][str(msg.chat.id)])
    else:
        chan = "\{} on ".format(findIRCUserFromMSG(msg, lookupUID=False))

    startMsg = startMsg.format(server=conf["IRC"]["server"].replace(".", "\."), user=msg.from_user.username, chan=chan)
    
    localServer["telegramids"][msg.from_user.username] = msg.from_user.id 
    
    bot.reply_to(msg, startMsg, parse_mode="MarkdownV2")


@bot.message_handler(commands=['setchan'], is_chat_admin=True)
def setChan(msg):
    global sock, localServer

    if msg.chat.type != "group": return

    args = msg.text.split()
    if len(args) > 1:
        bot.reply_to(msg, "Setting IRC channel to {}".format(args[1]))

        sendIRCPrivMsg(sock, conf["IRC"]["nick"], conf["IRC"]["logchan"], "Setting IRC channel to {} for Telegram group: {}".format(args[1], msg.chat.id))

        localServer["chanmap"][args[1]] = msg.chat.id
        localServer["chanmap"][msg.chat.id] = args[1]
    else:
        bot.reply_to(msg, "Usage: /setchan <IRC channel")

@bot.message_handler(commands=['conn'])
def conn(msg):
    global sock, localServer

    localServer["telegramids"][msg.from_user.username] = msg.from_user.id 

    if msg.chat.type != "group": return

    if not msg.from_user.username:
        bot.reply_to(msg, "Error: You currently don't have a username set.")
        return

    name = msg.from_user.first_name
    if msg.from_user.last_name:
        name += " " + msg.from_user.last_name

    if msg.from_user.username not in localServer["users"]:
        bot.reply_to(msg, "Creating IRC client for {}".format(msg.from_user.username))
        sendIRCPrivMsg(sock, conf["IRC"]["nick"], conf["IRC"]["logchan"], "Creating client for {} in Telegram group: {}".format(msg.from_user.username, msg.chat.id))
        addIRCUser(sock, msg.from_user.username, msg.from_user.username, "t.me/{}".format(msg.from_user.username), "+i", name)
        localServer["users"].append(msg.from_user.username)
        localServer["chans"][msg.from_user.username] = []
        localServer["names"][msg.from_user.username] = name
        
    if msg.from_user.username not in localServer["chans"]:
        joinIRCUser(sock, msg.from_user.username, localServer["chanmap"][str(msg.chat.id)], "v")
        localServer["chans"][msg.from_user.username].append(localServer["chanmap"][str(msg.chat.id)])
    else:
        bot.reply_to(msg, "You are already in this IRC channel.")

    writeLocalServerState()

@bot.message_handler(commands=['me'])
def tgSendIRCAction(msg):
    global sock, localServer

    localServer["telegramids"][msg.from_user.username] = msg.from_user.id

    if msg.from_user.username not in localServer["users"]:
        bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
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
    if msg.from_user.username not in localServer["users"]:
        bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
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

    localServer["telegramids"][msg.from_user.username] = msg.from_user.id

    if msg.chat.type != "private":
        bot.reply_to(msg, "This command is to be used when directly messaging me.")
        return

    if msg.from_user.username not in localServer["users"]:
        bot.reply_to(msg, "Error: You are not connected to IRC. Use /conn in a group I am in to connect.")
        return

    args = msg.text.split()
    if len(args) > 1:
        bot.reply_to(msg, "I will now send your messages in this chat to {}".format(args[1]))
        localServer["pms"][str(msg.from_user.id)] = args[1] 


@bot.message_handler(func=lambda message: True, content_types=['text'])
def tgSendIRCMsg(msg):
    global sock, localServer

    localServer["telegramids"][msg.from_user.username] = msg.from_user.id 

    if msg.chat.type == "group":
        if str(msg.chat.id) not in localServer["chanmap"]: return
        if msg.from_user.username not in localServer["users"]:
            bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
            return

        sendIRCPrivMsg(sock, msg.from_user.username, localServer["chanmap"][str(msg.chat.id)], msg.text)
        localServer["lastmsg"][msg.from_user.username] = int(time.time())
    elif msg.chat.type == "private":
        if msg.from_user.username not in localServer["users"]:
            bot.reply_to(msg, "Error: You are not connected to IRC. Use /conn in a group I am in to connect.")
            return
        
        if str(msg.from_user.id) not in localServer["pms"]:
            bot.reply_to(msg, "You have not created a private message with a user")
            return

        to = findIRCUserFromMSG(msg)

        bot.reply_to(msg, "Sending to {}".format(findIRCUserFromMSG(msg, lookupUID=False)))
        sendIRCPrivMsg(sock, msg.from_user.username, to, msg.text)
        localServer["lastmsg"][msg.from_user.username] = int(time.time())


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
    log(msg)
    sock.write(bytes("{}\r\n".format(msg), encoding='utf8'))

def addIRCUser(sock, user, nick, host, modes, real, isService=False):
    global lastID, localServer

    lastIDStr = str(lastID)
    calc = 6 - len(lastIDStr)
    ap = ""

    while calc != 0:
        ap += "0"
        calc -= 1
    
    localServer["uids"][nick] = conf["IRC"]["sid"] + ap + lastIDStr
    ruid = conf["IRC"]["sid"] + ap + lastIDStr

    if isService == True:
        modes += "o"

    ircOut(sock, ":{} UID {} {} {} {} {} {} 0.0.0.0 {} {} :{}".format(conf["IRC"]["sid"], ruid, int(time.time()), nick, host, host, user, time.time(), modes, real))

    if isService == True:
        ircOut(sock, ":{} OPERTYPE Service".format(ruid))

    lastID += 1

def joinIRCUser(sock, nick, chan, usermode):
    global remoteServer, localServer, membID

    if chan not in remoteServer["chans"].keys():
        remoteServer["chans"][chan] = {}
        remoteServer["chans"][chan]["ts"] = time.time()
        remoteServer["chans"][chan]["modes"] = "+nt"

    ircOut(sock, ":{} IJOIN {} {} {} :{}".format(localServer["uids"][nick], chan, membID, remoteServer["chans"][chan]["ts"], usermode))
    membID += 1

def rejoinTGUsers(sock):
    global localServer

    for user in localServer["users"]:
        addIRCUser(sock, user, user, "t.me/{}".format(user), "+i", localServer["names"][user])
        for chan in localServer["chans"][user]:
            joinIRCUser(sock, user, chan, "v")

def sendIRCAuth(sock):
    ircOut(sock, "CAPAB START 1205")
    ircOut(sock, "CAPAB END")
    ircOut(sock, "SERVER {} {} 0 {} :{}".format(conf["IRC"]["name"], conf["IRC"]["sendkey"], conf["IRC"]["sid"], conf["IRC"]["description"]))


def sendIRCBurst(sock):
    ircOut(sock, ":{} BURST".format(conf["IRC"]["sid"]))
    ircOut(sock, ":{} SINFO version: :1.0".format(conf["IRC"]["sid"]))
    ircOut(sock, ":{} SINFO fullversion :TeleServ 1.0 {} :[{}] {}".format(conf["IRC"]["sid"], conf["IRC"]["name"], conf["IRC"]["sid"], conf["IRC"]["network"]))
    addIRCUser(sock, conf["IRC"]["nick"], conf["IRC"]["nick"], conf["IRC"]["name"], "+i", "Telegram IRC Bridge", isService=True)
    ircOut(sock, ":{} ENDBURST".format(conf["IRC"]["sid"]))

def sendIRCPrivMsg(sock, nick, chan, msg):
    global localServer

    ircOut(sock, ":{} PRIVMSG {} :{}".format(localServer["uids"][nick], chan, msg))

def sendIRCNotice(sock, nick, chan, msg):
    global localServer

    ircOut(sock, ":{} NOTICE {} :{}".format(localServer["uids"][nick], chan, msg))

def ircPrivMsgHandler(uid, target, msg):
    global sock, remoteServer, localServer

    print(target)

    nick = uid

    for n in localServer["uids"]:
        if localServer["uids"][n] == target:
            nick = n

    if nick == uid and uid in remoteServer["uids"]:
        nick = remoteServer["uids"][uid]["nick"]

    print("DEBUG nick = {} target = {}".format(nick, target))

    # strip mIRC formatting
    msg = re.sub(r"[\x02\x1F\x0F\x16]|\x03(\d\d?(,\d\d?)?)?", "", msg)
    
    if target not in localServer["chanmap"] and nick not in localServer["telegramids"]:
        if target == localServer["uids"][conf["IRC"]["nick"]]:
            if uid not in remoteServer["opers"]:
                sendIRCNotice(sock, conf["IRC"]["nick"], nick, "Access denied.")
                return

            if (msg == "help" or msg == "HELP"):
                sendIRCNotice(sock, conf["IRC"]["nick"], nick, "***** \x02TeleServ Help\x02 *****")
                sendIRCNotice(sock, conf["IRC"]["nick"], nick, "\x02USERLIST\x02    List of Telegram users connected and their IRC nicks.")
                sendIRCNotice(sock, conf["IRC"]["nick"], nick, "\x02WHOIS\x02       Gives info about a Telegram user.")
                sendIRCNotice(sock, conf["IRC"]["nick"], nick, "\x02RAW\x02         Sends raw data to server socket. (Only use if you know how.)")
                sendIRCNotice(sock, conf["IRC"]["nick"], nick, "**** \x02End of Help\x02 *****")
            elif (msg == "USERLIST" or msg == "userlist"):
                sendIRCNotice(sock, conf["IRC"]["nick"], nick, "***** \x02Telegram Users\x02 *****")
                for user in localServer["users"]:
                    sendIRCNotice(sock, conf["IRC"]["nick"], nick, "@{} is connected as {} in channels: {}".format(user, user, " ".join(localServer["chans"][user])))
            elif ("RAW" in msg or "raw" in msg):
                tmp = msg.split(" ")
                ircOut(sock, " ".join(tmp[1:]))
    elif nick in localServer["telegramids"]:
        to = localServer["telegramids"][nick]

        if uid in remoteServer["uids"]:
            senderNick = remoteServer["uids"][uid]["nick"]
        else:
            senderNick = uid
            for n in localServer["uids"]:
                if uid == localServer["uids"][n]:
                    senderNick = n

        if re.search(r"ACTION (.*)", msg):
            msg = re.sub("ACTION ", "", msg)
            bot.send_message(to, "* {}{}".format(senderNick, msg))
        else:
            bot.send_message(to, "<{}> {}".format(senderNick, msg))        
    else:
        to = localServer["chanmap"][target]

        if re.search(r"ACTION (.*)", msg):
            msg = re.sub("ACTION ", "", msg)
            bot.send_message(to, "* {}{}".format(nick, msg))
        else:
            bot.send_message(to, "<{}> {}".format(nick, msg))


def handleSocket(rawdata, sock):
    global initalBurstSent, prevline, logChannelJoined

    rawdata = ":".join(rawdata.split(":"))

    for data in rawdata.split("\n"):
        if data == "": continue

        if data[0] != ":":
            data = prevline + data

        if re.search(r":(.*) :(.*)", data):
            log("IRC RAW: {}".format(data))

            matches = re.search(r"CAPAB (\w+) :(.*)", data)
            if matches:
                matches = matches.groups()
                remoteServer["capab"][matches[0]] = matches[1].split(" ")

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
                remoteServer["chans"][matches[1]]["users"] = matches[4].split(" ")

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

            matches = re.search(r":(.*?) PRIVMSG (.*?) :(.*)", data)
            if matches:
                matches = matches.groups()

                if re.search(r"\x01VERSION\x01", matches[2]):
                    ircOut(sock, ":{} NOTICE {} :VERSION TeleServ v1.0: Telegram to IRC bridge (https://github.com/ablakely/TeleServ) by Aaron Blakely".format(matches[1], matches[0]))
                else:
                    ircPrivMsgHandler(matches[0], matches[1], matches[2])

            matches = re.search(r":(.*?) IDLE :(.*)", data)
            if matches:
                matches = matches.groups()

                for k in localServer["uids"]:
                    if localServer["uids"][k] == matches[1]:
                        then = localServer["lastmsg"][k]
                        calc = int(time.time()) - then

                        ircOut(sock, ":{} IDLE {} :{}".format(matches[1], matches[0], calc))

            matches = re.search(r":(.*?) MOTD :(.*)", data)
            if matches:
                matches = matches.groups()

                motdSplit = motd.split("\n")
                ircOut(sock, "NUM {} {} 375 :- {} Message of the day -".format(conf["IRC"]["sid"], matches[0], conf["IRC"]["name"]))
                for line in motdSplit:
                    ircOut(sock, "NUM {} {} 372 :- {}".format(conf["IRC"]["sid"], matches[0], line))
                ircOut(sock, "NUM {} {} 376 :End of Message of the Day.".format(conf["IRC"]["sid"], matches[0]))

            matches = re.search(r":(.*?) NICK (.*?) :(.*)", data)
            if matches:
                matches = matches.groups()
                remoteServer["uids"][matches[0]]["nick"] = matches[1]

            matches = re.search(r":(.*?) OPERTYPE :(.*)", data)
            if matches:
                matches = matches.groups()
                remoteServer["opers"].append(matches[0])

        if re.search(r":(.*?) PING (.*)", data):
            matches = re.search(r":(.*?) PING (.*)", data)
            if matches:
                matches = matches.groups()
                ircOut(sock, ":{} PONG :{}".format(conf["IRC"]["sid"], matches[0]))

                if logChannelJoined == False:
                    logChannelJoined = True
                    joinIRCUser(sock, conf["IRC"]["nick"], conf["IRC"]["logchan"], "o")
                    rejoinTGUsers(sock)

        prevline = data


def tgPoll():
    bot.infinity_polling(allowed_updates=util.update_types)

def main():
    global sock, conf

    log("Creating telegram polling thread.")
    threading.Thread(target=tgPoll, name='bot_infinity_polling', daemon=True).start()

    log("Creating SSL connection to {}".format(conf["IRC"]["server"]))
    rawsock = socket.socket(socket.AF_INET)
    context = ssl._create_unverified_context()
    sock = context.wrap_socket(rawsock, server_hostname=conf["IRC"]["server"])

    try:
        sock.connect((conf["IRC"]["server"], conf["IRC"]["port"]))
        sendIRCAuth(sock)

        print("")
        while True:
            data = sock.recv().decode()
            if not data: break

            handleSocket(data, sock)

    finally:
        print("\nWriting bridgestates.json")
        writeLocalServerState()

        print("Error: IRC server closed the connection, exiting.")
        sock.close()

if __name__ == '__main__':
    main()