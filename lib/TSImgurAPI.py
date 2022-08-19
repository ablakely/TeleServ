# TSImgurAPI.py: Imgur API module for TeleServ
#
# This implements an upload queue system to handle the async calls from pyTelegramAPI
# It does so by using a thread that checks time elapsed since last image from
# telegram user and if it's been longer than 4 seconds it will upload all images
# from the user in the queue to an imgur album and then call a callback function
# to send the link to IRC
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

from imgurpython import ImgurClient
import threading
import time
import os

class TSImgurAPI():
    def __init__(self, opts, JSONParser):
        if "enabled" in opts:
            if opts["enabled"] == False:
                self.ENABLED = False
                return
            else:
                self.ENABLED = True
        else:
            self.ENABLED = False
            return

        if "API_ID" not in opts:
            raise ValueError("Config option: Imgur API_ID is not defined.")
        if "API_SECRET" not in opts:
            raise ValueError("Config option: Imgur API_SECRET is not defined.")

        self.TSJSON = JSONParser
        self.SHUTDOWN = False
        self.uploadQueue = {}

        state = JSONParser.loadLocalServerState()

        if "IMGURCREDS" not in state:
            self.CLIENT = ImgurClient(opts["API_ID"], opts["API_SECRET"])
            self.AUTHORIZED = False
        else:
            self.CLIENT = ImgurClient(opts["API_ID"], opts["API_SECRET"], state["IMGURCREDS"]["refresh_token"])
            self.CLIENT.set_user_auth(state["IMGURCREDS"]["access_token"], state["IMGURCREDS"]["refresh_token"])
            self.AUTHORIZED = True

            print("Creating imgur uploader thread")
            self.startUploadThread()

    def getAuthURL(self):
        return self.CLIENT.get_auth_url('pin')

    def thread_wrapper(self):
        while True:
            if self.SHUTDOWN == True: break

            time.sleep(0.1)

            for user in dict(self.uploadQueue):
                if time.time() - self.uploadQueue[user]["last_update"] > 30:
                    # If no images from Telegram have been added to queue in more than 30
                    # seconds it's safe to assume the end of the telegram post? delete user
                    # dict from queue

                    del(self.uploadQueue[user])
                    return
                elif self.uploadQueue[user]["started"] == True: 
                    return
                elif time.time() - self.uploadQueue[user]["last_update"] > 4:
                    imgdata = []
                    self.uploadQueue[user]["started"] == True

                    for path in self.uploadQueue[user]["imgs"]:
                        imgdata.append(self.CLIENT.upload_from_path(f"/tmp/{path}", anon=False))

                    tmp = user.split(":")
                    forStr = f"{tmp[0]} in {tmp[1]}"

                    config = {
                        "title": "Uploaded by TeleServ for {} at {}".format(forStr, time.strftime("%I:%M %p on %d-%m-%Y", time.localtime())),
                        "description": self.uploadQueue[user]["desc"],
                        "privacy": "hidden"
                    }

                    albumdata = self.CLIENT.create_album(config)

                    ids = [data['id'] for data in imgdata]
                    ids.reverse()

                    self.CLIENT.album_add_images(albumdata['id'], ids)

                    albumdata["cnt"] = len(ids)

                    self.uploadQueue[user]["callback"](self.uploadQueue[user]["msg"], albumdata)

                    for path in self.uploadQueue[user]["imgs"]:
                        os.remove(f"/tmp/{path}")

                    del(self.uploadQueue[user])


    def startUploadThread(self):
        threading.Thread(target=self.thread_wrapper, name="imgur_uploader", daemon=False).start()

    def getAuthTokens(self, pin):
        self.CREDENTIALS = self.CLIENT.authorize(pin, 'pin')
        self.CLIENT.set_user_auth(self.CREDENTIALS["access_token"], self.CREDENTIALS["refresh_token"])
        self.AUTHORIZED = True

        self.TSJSON.setState({"IMGURCREDS": self.CREDENTIALS})
        
        print("Starting imgur uploader thread...")
        self.startUploadThread()

    def upload(self, files, username, source, caption, msg, callback):
        if self.ENABLED == False: return

        if source != False:
            desc = caption + "\n\nUploaded for {} in {} by TeleServ".format(username, source)
            username = f"{username}:{source}"
        else:
            desc = caption + "\n\nUploaded for {} by TeleServ".format(username)
            username = f"{username}:PM"

        if username not in self.uploadQueue:
            self.uploadQueue[username] = {}
            self.uploadQueue[username]["imgs"] = []
            self.uploadQueue[username]["last_update"] = time.time()
        else:
            self.uploadQueue[username]["last_update"] = time.time()

        self.uploadQueue[username]["desc"] = desc
        self.uploadQueue[username]["callback"] = callback
        self.uploadQueue[username]["msg"] = msg
        self.uploadQueue[username]["started"] = False

        for path in files:
            self.uploadQueue[username]["imgs"].append(path)


    def isAuthed(self):
        if self.ENABLED == False: return True

        return self.AUTHORIZED

    def stopUploadThread(self):
        self.SHUTDOWN = True