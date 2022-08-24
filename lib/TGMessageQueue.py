# TelegramAPI.py: Telegram Message Queue module for TeleServ
#
# This implements a message queue system to handle avoid triggering
# API call rate limits, suck as error 429.  It does so by adding messages
# to a queue and then sends them to Telegram is a safe rate.
#
# TeleServ - Telegram to IRC bridge server
#
# Copyright (c) 2022 Aaron Blakely
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Support: https://webchat.ephasic.org/?join=ephasic

import re
import threading
import time

class TGMessageQueue():
    def __init__(self, TGBot):
        self.bot = TGBot
        self.SHUTDOWN = False

        self.msgQueue = []
        self.lastMessageTime = 0
        self.timeout = 0
        
        print("Creating message queue thread")
        self.startMessageQueueThread()

    def reply_to(self, msg, text, parse_mode=None):
        self.msgQueue.append({
            "type": "REPLY",
            "msg":  msg,
            "text": text,
            "mode": parse_mode,
            "time": int(time.time())
        })

    def send_message(self, to, text, parse_mode=None):
        self.msgQueue.append({
            "type": "MESSAGE",
            "to":  to,
            "text": text,
            "mode": parse_mode,
            "time": int(time.time())
        })

    def startMessageQueueThread(self):
        threading.Thread(target=self.thread_wrapper, name="message_queue", daemon=False).start()

    def stopMessageQueueThread(self):
        self.SHUTDOWN = True

    def flushQueue(self):
        burst = {}
        
        i = 0
        while True:
            if i >= len(self.msgQueue): break

            if self.msgQueue[i]["type"] == "MESSAGE" and self.msgQueue[i]["mode"] == None:
                if self.msgQueue[i]["to"] not in burst:
                    burst[self.msgQueue[i]["to"]] = ""

                burst[self.msgQueue[i]["to"]] += f"{self.msgQueue[i]['text']}\n"
                del(self.msgQueue[i])
                continue

            i += 1

        for to in burst:
            self.bot.send_message(to, burst[to])

    def thread_wrapper(self):
        while True:
            if self.SHUTDOWN == True: break

            time.sleep(0.1)

            i = 0

            while True:
                if len(self.msgQueue) == 0: break

                if self.msgQueue[i]["type"] == "REPLY":
                    try:
                        self.bot.reply_to(self.msgQueue[i]["msg"], self.msgQueue[i]["text"], parse_mode=self.msgQueue[i]["mode"])
                    except Exception as e:
                        if re.search(r"A request to the Telegram API was unsuccessful. Error code: 429. Description: Too Many Requests", str(e)): 
                            secs = int(str(e).split(" ")[-1])
                            print(f"TelegramMSGQueue: Rate limit exceeded, sleeping thread for {secs} seconds.")

                            time.sleep(secs)
                            self.bot.reply_to(self.msgQueue[i]["msg"], self.msgQueue[i]["text"], parse_mode=self.msgQueue[i]["mode"])
                        else:
                            print(f"TGMessageQueue Error: {e}")

                    finally:
                        del(self.msgQueue[i])
                        continue
                elif self.msgQueue[i]["type"] == "MESSAGE":
                    try:
                        self.bot.send_message(self.msgQueue[i]["to"], self.msgQueue[i]["text"], parse_mode=self.msgQueue[i]["mode"])
                    except Exception as e:
                        if re.search(r"A request to the Telegram API was unsuccessful. Error code: 429. Description: Too Many Requests", str(e)): 
                            secs = int(str(e).split(" ")[-1])
                            print(f"TelegramMSGQueue: Rate limit exceeded, sleeping thread for {secs} seconds.")

                            time.sleep(secs)
                            self.flushQueue()
                            continue
                        else:
                            print(f"TGMessageQueue Error: {e}")

                    finally:
                        if len(self.msgQueue) == 0: break

                        del(self.msgQueue[i])
                        continue

