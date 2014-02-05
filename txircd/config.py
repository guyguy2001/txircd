import yaml

_defaults = {
    "bind_client": [ "tcp:6667:interface={::}" ],
    "bind_server": []
}

class Config(object):
    def __init__(self, configFileName):
        self._configData = {}
        self._readConfig(configFileName)
        for key, val in _defaults.iteritems():
            if key not in self._configData:
                self._configData[key] = val
    
    def _readConfig(self, fileName):
        try:
            with open(fileName, 'r') as configFile:
                configData = yaml.safe_load(configFile)
        except Exception as e:
            raise ConfigReadError (e)
        for key, val in configData.iteritems():
            if key != "include" and key not in self._configData:
                self._configData[key] = val
        if "include" in configData:
            for fileName in configData["include"]:
                self._readConfig(fileName)
    
    def __len__(self):
        return len(self._configData)
    
    def __getitem__(self, key):
        return self._configData[key]
    
    def __setitem__(self, key, value):
        self._configData[key] = value
    
    def getWithDefault(self, key, defaultValue):
        try:
            return self._configData[key]
        except KeyError:
            return defaultValue

class ConfigReadError(Exception):
    def __init__(self, desc):
        self.desc = desc
    
    def __str__(self):
        return "Error reading configuration file: {}".format(self.desc)