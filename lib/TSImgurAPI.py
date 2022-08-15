# TSImgurAPI.py: Imgur API module for TeleServ
#
# TeleServ - Telegram to IRC bridge server
#
# Copyright (c) 2022 Aaron Blakely
# Support: https://webchat.ephasic.org/?join=ephasic

from imgurpython import ImgurClient
import time

class TSImgurAPI():
    def __init__(self, opts):
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

        self.CLIENT = ImgurClient(opts["API_ID"], opts["API_SECRET"])

    def uploadTG(self, file, username, source):
        if self.ENABLED == False: return

        if source != False:
            desc = "Uploaded for {} in {} by TeleServ".format(username, source)
        else:
            desc = "Uploaded for {} by TeleServ".format(username)

        config = {
            "album": None,
            "name": "{}: {}".format(username,  time.strftime("%H:%M:%S %d-%m-%Y", time.localtime())),
            "title": "{}: {}".format(username,  time.strftime("%H:%M:%S %d-%m-%Y", time.localtime())),
            "description": desc
        }

        return self.CLIENT.upload_from_path(file, config=config, anon=True)
