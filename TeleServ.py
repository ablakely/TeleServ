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

# Globals
lastID = 0
sock = {}
prevline = ""
initalBurstSent = False
logChannelJoined = False

remoteServer = {}
remoteServer["capab"] = {}
remoteServer["chans"] = {}
remoteServer["uids"]  = {}

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

#
# Utility functions
#
def log(msg):
    if conf["DEBUG"] == True: print(msg.strip())

#
# Telegram connection
#

@bot.message_handler(commands=['start'])
def startMsg(msg):
    global localServer, conf

    startMsg = """
    Hi\! I am TeleServ, an IRC bridge bot by [ablakely](https://github.com/ablakely)
I am currently linking this group to: 
`{chan}{server}`
    
My commands are:
 /setchan `\<channel\>` \- Set destination IRC channel for group
 /conn \- Creates an IRC client with your username \({user}\)
 /me `\<action\>`/s \- Action command
    
Any other messaged will be relayed to the IRC channel\."""

    chan = ""
    if msg.chat.id in localServer["chanmap"]:
        chan = "\{} ".format(localServer["chanmap"][msg.chat.id])
    startMsg = startMsg.format(server=conf["IRC"]["server"].replace(".", "\."), user=msg.from_user.username, chan=chan)
    
    print(startMsg)
    
    bot.reply_to(msg, startMsg, parse_mode="MarkdownV2")


@bot.message_handler(commands=['setchan'], is_chat_admin=True)
def setChan(msg):
    global sock, localServer

    if msg.chat.type != "group": return

    args = msg.text.split()
    if len(args) > 1:
        bot.reply_to(msg, "Setting IRC channel to {}".format(args[1]))

        sendIRCPrivMsg(sock, "TeleServ", "#network", "Setting IRC channel to {} for Telegram group: {}".format(args[1], msg.chat.id))

        localServer["chanmap"][args[1]] = msg.chat.id
        localServer["chanmap"][msg.chat.id] = args[1]

@bot.message_handler(commands=['conn'])
def conn(msg):
    global sock, localServer

    if not msg.from_user.username:
        bot.reply_to(msg, "Error: You currently don't have a username set.")
        return

    name = msg.from_user.first_name
    if msg.from_user.last_name:
        name += " " + msg.from_user.last_name

    if msg.from_user.username not in localServer["users"]:
        bot.reply_to(msg, "Creating IRC client for {}".format(msg.from_user.username))
        sendIRCPrivMsg(sock, "TeleServ", "#network", "Creating client for {} in Telegram group: {}".format(msg.from_user.username, msg.chat.id))
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

    if msg.chat.id not in localServer["chanmap"].keys(): return

    tmp = msg.text.split(" ")
    tmp.pop(0)

    tmp = " ".join(tmp)

    sendIRCPrivMsg(sock, msg.from_user.username, localServer["chanmap"][msg.chat.id], "\001ACTION {}\001".format(tmp))

@bot.message_handler(func=lambda message: True, content_types=['text'])
def tgSendIRCMsg(msg):
    global sock, localServer

    if str(msg.chat.id) not in localServer["chanmap"]: return
    if msg.from_user.username not in localServer["users"]:
        bot.reply_to(msg, "You haven't join the IRC server yet, please use /conn")
        return

    sendIRCPrivMsg(sock, msg.from_user.username, localServer["chanmap"][str(msg.chat.id)], msg.text)


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
    sock.write(bytes("{}\r\n".format(msg), encoding='ascii'))

def addIRCUser(sock, user, nick, host, modes, real):
    global lastID, localServer

    lastIDStr = str(lastID)
    calc = 6 - len(lastIDStr)
    ap = ""

    while calc != 0:
        ap += "0"
        calc -= 1
    
    localServer["uids"][nick] = conf["IRC"]["sid"] + ap + lastIDStr
    ruid = conf["IRC"]["sid"] + ap + lastIDStr

    ircOut(sock, ":{} UID {} {} {} {} {} {} 0.0.0.0 {} {} :{}".format(conf["IRC"]["sid"], ruid, time.time(), nick, host, host, user, time.time(), modes, real))
    lastID += 1

def joinIRCUser(sock, nick, chan, usermode):
    global remoteServer, localServer

    if chan not in remoteServer["chans"].keys():
        remoteServer["chans"][chan] = {}
        remoteServer["chans"][chan]["ts"] = time.time()
        remoteServer["chans"][chan]["modes"] = "+nt"

    ircOut(sock, ":{} FJOIN {} {} {} :{},{}".format(conf["IRC"]["sid"], chan, remoteServer["chans"][chan]["ts"], remoteServer["chans"][chan]["modes"], usermode, localServer["uids"][nick]))

def rejoinTGUsers(sock):
    global localServer

    for user in localServer["users"]:
        addIRCUser(sock, user, user, "t.me/{}".format(user), "+i", localServer["names"][user])
        for chan in localServer["chans"][user]:
            joinIRCUser(sock, user, chan, "v")

def sendIRCAuth(sock):
    ircOut(sock, "PASS {} TS6 :{}".format(conf["IRC"]["sendkey"], conf["IRC"]["sid"]))
    ircOut(sock, "CAPAB QS ENCAP EX IE CHW KNOCK SAVE EUID SERVICES RSFNC")
    ircOut(sock, "SERVER {} {} 0 {} :{}".format(conf["IRC"]["name"], conf["IRC"]["sendkey"], conf["IRC"]["sid"], conf["IRC"]["description"]))


def sendIRCBurst(sock):
    ircOut(sock, ":{} BURST".format(conf["IRC"]["sid"]))
    ircOut(sock, ":{} VERSION :Telebridge-1.0 {} :{}".format(conf["IRC"]["sid"], conf["IRC"]["name"], conf["IRC"]["network"]))
    addIRCUser(sock, "teleserv", "TeleServ", "telegram.ephasic.org", "+i", "Telegram IRC Bridge")
    ircOut(sock, ":{} ENDBURST".format(conf["IRC"]["sid"]))

def sendIRCPrivMsg(sock, nick, chan, msg):
    global localServer

    print("DEBUG: nick = {}, chan = {}, msg = {}".format(nick, chan, msg))

    ircOut(sock, ":{} PRIVMSG {} :{}".format(localServer["uids"][nick], chan, msg))

def sendIRCNotice(sock, nick, chan, msg):
    global localServer

    ircOut(sock, ":{} NOTICE {} :{}".format(localServer["uids"][nick], chan, msg))

def ircPrivMsgHandler(uid, target, msg):
    global sock, remoteServer, localServer

    if uid in remoteServer["uids"]:
        nick = remoteServer["uids"][uid]["nick"]
    else:
        nick = uid
    
    if target not in localServer["chanmap"].keys():
        if target == localServer["uids"]["TeleServ"]:
            if (msg == "help" or msg == "HELP"):
                sendIRCNotice(sock, "TeleServ", nick, "***** \x02TeleServ Help\x02 *****")
                sendIRCNotice(sock, "TeleServ", nick, "\x02USERLIST\x02    List of Telegram users connected and their IRC nicks.")
                sendIRCNotice(sock, "TeleServ", nick, "\x02WHOIS\x02       Gives info about a Telegram user.")
                sendIRCNotice(sock, "TeleServ", nick, "**** \x02End of Help\x02 *****")
            elif (msg == "USERLIST" or msg == "userlist"):
                sendIRCNotice(sock, "TeleServ", nick, "***** \x02Telegram Users\x02 *****")
                for user in localServer["users"]:
                    sendIRCNotice(sock, "TeleServ", nick, "@{} is connected as {} in channels: {}".format(user, user, " ".join(localServer["chans"][user])))
    else:
        to = localServer["chanmap"][target]

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
                ircPrivMsgHandler(matches[0], matches[1], matches[2])

        if re.search(r":(.*?) PING (.*?) (.*)", data):
            matches = re.search(r":(.*?) PING (.*?) (.*)", data)
            if matches:
                matches = matches.groups()
                ircOut(sock, ":{} PONG {} :{}".format(conf["IRC"]["sid"], matches[2].replace(":", ""), matches[1]))

                if logChannelJoined == False:
                    logChannelJoined = True
                    joinIRCUser(sock, "TeleServ", "#network", "o")
                    rejoinTGUsers(sock)

        prevline = data


def tgPoll():
    bot.infinity_polling(allowed_updates=util.update_types)

def main():
    global sock, conf

    log("Debug: Creating telegram polling thread.")
    threading.Thread(target=tgPoll, name='bot_infinity_polling', daemon=True).start()

    log("Debug: Creating SSL connection to {}".format(conf["IRC"]["server"]))
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