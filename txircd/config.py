import yaml

class Config(object):
	def __init__(self, ircd, configFileName):
		self.ircd = ircd
		self.fileName = configFileName
	
	def reload(self):
		newConfig = self._readConfig(self.fileName)
		self.ircd.verifyConfig(newConfig)
		self._configData = newConfig
	
	def _readConfig(self, fileName):
		configData = {}
		try:
			with open(fileName, "r") as configFile:
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

	def __setitem__(self, key, value):
		self._configData[key] = value

	def __iter__(self):
		return iter(self._configData)
	
	def get(self, key, defaultValue):
		"""
		Allows you to get a key from the configuration with a default value if
		the configuration key does not exist.
		"""
		try:
			return self._configData[key]
		except KeyError:
			return defaultValue

class ConfigError(Exception):
	pass

class ConfigReadError(ConfigError):
	def __init__(self, fileName, desc):
		self.fileName = fileName
		self.desc = desc
	
	def __str__(self):
		return "Error reading configuration file {}: {}".format(self.fileName, self.desc)

class ConfigValidationError(ConfigError):
	def __init__(self, key, desc):
		self.key = key
		self.desc = desc

	def __str__(self):
		return "Error validating configuration value {}: {}".format(self.key, self.desc)