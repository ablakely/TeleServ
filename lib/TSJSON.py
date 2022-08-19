# TSJSON.py: JSON config and states module for TeleServ
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


import json
from os.path import exists

class TSJSON():
    def __init__(self, conf, state):
        self.confFile = conf
        self.stateFile = state
        self.appends    = []
        self.localServer = {}

    def readCfg(self):
        f = open(self.confFile)
        ret = json.load(f)
        f.close()

        if "enableRAW" not in ret:
            ret["enableRAW"] = False
        elif ret["enableRAW"] == True:
            print("[WARNING] The RAW command is enabled, this is not recommended for production use and should only be used by someone that knows how.")

        return ret

    def loadLocalServerState(self):
        if bool(self.localServer) != False:
            return self.localServer

        if exists(self.stateFile):
            f = open(self.stateFile)
            ret = json.load(f)
            f.close()
        else:
            ret = {}
            ret["uids"] = {}
            ret["chanmap"] = {}

        self.localServer = ret
        return ret

    def setState(self, state):
        self.appends.append(state)

    def getState(self, state):
        if state in self.localServer:
            return [state]

        return None

    def update(self, localServer):
        self.localServer = localServer

    def writeLocalServerState(self):
        if len(self.appends) > 0:
            for state in self.appends:
                for key in state:
                    localServer[key] = state[key]

            self.appends = []

        f = open(self.stateFile, "w")
        json.dump(self.localServer, f, indent=2)
        f.close()