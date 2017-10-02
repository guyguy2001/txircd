# This file converts data.db in a way that can be read by Python 3.

# SETUP: We need to encode datetimes
from datetime import datetime

def timestamp(time):
	unixEpoch = datetime.utcfromtimestamp(0)
	return (time - unixEpoch).total_seconds()

def encodeDatetime(obj):
	if isinstance(obj, datetime):
		return {
			"type": "*json-datetime",
			"value": timestamp(obj)
		}
	raise TypeError("Could not be serialized")

# SETUP: Open the data.db file
import argparse, json, shelve, sys
argumentParser = argparse.ArgumentParser(description="Upgrades txircd's data.db from the 0.4 format to the 0.5 format (Python 2 segment).")
argumentParser.add_argument("--datafile", dest="datafile", help="The location of the data file (default: data.db)", default="data.db")

args = argumentParser.parse_args()

storage = None
try:
	storage = shelve.open(args.datafile)
except Exception as err:
	print("Error opening data file: {}".format(err))
	sys.exit(1)

# CONVERT: Save in .json format
storageData = {}
for key, value in storage.items():
	storageData[key] = value
with open("{}.json".format(args.datafile), "w") as midFile:
	json.dump(storageData, midFile, default=encodeDatetime)

# SHUTDOWN: Close data.db
storage.close()