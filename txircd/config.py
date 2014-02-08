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
            raise ConfigReadError (fileName, e)
        for key, val in configData.iteritems():
            if key == "include":
                continue
            if key not in self._configData:
                self._configData[key] = val
            elif not isinstance(self._configData[key], basestring): # Let's try to merge them if they're lists
                if isinstance(val, basestring):
                    raise ConfigReadError(fileName, "The included configuration file tried to merge a non-string with a string.")
                try: # Make sure both things we're merging are still iterable types
                    iter(self._configData[key])
                    iter(val)
                except TypeError:
                    pass # Simply don't merge them if they're not
                else:
                    try:
                        self._configData[key] += val
                    except TypeError: # They can't be merged with +=; we'll try them as dicts and then fail if they're not that
                        try:
                            for subkey, subval in val.iteritems():
                                if subkey not in self._configData[key]:
                                    self._configData[key][subkey] = subval
                        except AttributeError, TypeError: # They weren't both dicts in this case, but were still both iterable; needs resolved by user.
                            raise ConfigReadError(fileName, "The variable {} could not successfully be merged.".format(key))
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
    def __init__(self, fileName, desc):
        self.fileName = fileName
        self.desc = desc
    
    def __str__(self):
        return "Error reading configuration file {}: {}".format(self.fileName, self.desc)