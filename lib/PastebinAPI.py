# PastebinAPI.py: Pastebin API module for TeleServ
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


import requests
import time

class TSPastebinAPI():
    def __init__(self, opts):
        if "pastebinLongMessages" in opts:
            if opts["pastebinLongMessages"] == False:
                self.ENABLED = False
                return

        if "API_KEY" not in opts:
            raise ValueError("Config option: Pastebin API key is not defined.")
        if "Username" not in opts:
            raise ValueError("Config option: Pastebin Username is not defined.")
        if "Password" not in opts:
            raise ValueError("Config option: Pastebin Password is not defined.")
        if "messageLength" not in opts:
            raise ValueError("Config option: Pastebin message length is not defined.")

        if "privacy" not in opts:
            opts["privacy"] = "0"

        if "expireTime" not in opts:
            opts["expireTime"] = "1W"

        # Check if our given credentials are correct
        login = requests.post("https://pastebin.com/api/api_login.php", data={
            "api_dev_key": opts["API_KEY"],
            "api_user_name": opts["Username"],
            "api_user_password": opts["Password"]
        })

        if login.status_code == 200:
            self.API_KEY  = opts["API_KEY"]
            self.USERNAME = opts["Username"]
            self.PASSWORD = opts["Password"]
            self.MSGLEN   = opts["messageLength"]
            self.PRIVACY  = str(opts["privacy"])
            self.EXPIRES  = opts["expireTime"]
            self.TOKEN    = login.text
            self.ENABLED  = True
        else:
            raise ValueError("Invalid credentials for pastebin.com in conf.json")

    def paste(self, content):
        if self.ENABLED == False:
            return False

        paste = requests.post("https://pastebin.com/api/api_post.php", data={
            "api_option": "paste",
            "api_dev_key": self.API_KEY,
            "api_paste_code": content,
            "api_paste_name": time.strftime("%H:%M:%S %d-%m-%Y", time.localtime()),
            "api_paste_expire_date": self.EXPIRES,
            "api_user_key": self.TOKEN,
            "api_paste_format": "text",
            "api_paste_private": self.PRIVACY
        })

        if "https://pastebin.com" in paste.text:
            return paste.text
        else:
            raise ValueError(paste.text.strip())

    def enabled(self):
        return self.ENABLED

    def msglen(self):
        return self.MSGLEN