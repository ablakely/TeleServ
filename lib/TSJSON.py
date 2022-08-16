import json
from os.path import exists

class TSJSON():
    def __init__(self, conf, state):
        self.confFile = conf
        self.stateFile = state
        self.appends    = []

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
        if exists(self.stateFile):
            f = open(self.stateFile)
            ret = json.load(f)
            f.close()
        else:
            ret = {}
            ret["uids"] = {}
            ret["chanmap"] = {}

        return ret

    def appendState(self, state):
        self.appends.append(state)

    def writeLocalServerState(self, localServer):
        if len(self.appends) > 0:
            for state in self.appends:
                for key in state:
                    localServer[key] = state[key]

            self.appends = []

        f = open(self.stateFile, "w")
        json.dump(localServer, f, indent=2)
        f.close()