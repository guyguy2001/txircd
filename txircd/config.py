import yaml

_defaults = {
	"bind_client": [ "tcp:6667:interface={::}" ],
	"bind_server": [],
	"modules": []
}

_required = []

_requiredValue = [
	"server_name",
	"server_description",
	"network_name"
]

_formatValue = {
	"network_name": lambda name: name[:32]
}

class Config(object):
	def __init__(self, configFileName):
		self.fileName = configFileName
	
	def reload(self):
		newConfig = self._readConfig(self.fileName)
		for key, val in _defaults.iteritems():
			if key not in newConfig:
				newConfig[key] = val
		for item in _required:
			if item not in newConfig:
				raise ConfigReadError (self.fileName, "Required item {} not found in configuration file.".format(item))
		for item in _requiredValue:
			if item not in newConfig:
				raise ConfigReadError (self.fileName, "Required item {} not found in configuration file.".format(item))
			if not newConfig[item]:
				raise ConfigReadError (self.fileName, "Required item {} found in configuration file with no value.".format(item))
		for item, formatFunc in _formatValue.iteritems():
			if item in newConfig:
				newConfig[item] = formatFunc(newConfig[item])
		self._configData = newConfig
	
	def _readConfig(self, fileName):
		configData = {}
		try:
			with open(fileName, 'r') as configFile:
				configData = yaml.safe_load(configFile)
		except Exception as e:
			raise ConfigReadError (fileName, e)
		if "include" in configData:
			for fileName in configData["include"]:
				includeConfig = self._readConfig(fileName)
				for key, val in includeConfig.iteritems():
					if key not in configData:
						configData[key] = val
					elif not isinstance(configData[key], basestring): # Let's try to merge them if they're collections
						if isinstance(val, basestring):
							raise ConfigReadError(fileName, "The included configuration file tried to merge a non-string with a string.")
						try: # Make sure both things we're merging are still iterable types (not numbers or whatever)
							iter(configData[key])
							iter(val)
						except TypeError:
							pass # Just don't merge them if they're not
						else:
							try:
								configData[key] += val # Merge with the + operator
							except TypeError: # Except that some collections (dicts) can't
								try:
									for subkey, subval in val.iteritems(): # So merge them manually
										if subkey not in configData[key]:
											configData[key][subkey] = subval
								except (AttributeError, TypeError): # If either of these, they weren't both dicts (but were still iterable); requires user to resolve
									raise ConfigReadError(fileName, "The variable {} could not be successfully merged across files.".format(key))
			del configData["include"]
		return configData
	
	def __len__(self):
		return len(self._configData)
	
	def __getitem__(self, key):
		return self._configData[key]
	
	def __iter__(self):
		return iter(self._configData)
	
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