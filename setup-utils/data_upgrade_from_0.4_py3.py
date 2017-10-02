# This file upgrades data.db from the 0.4 format data to 0.5 format data.

# SETUP: Convert datetime type placeholders back to datetimes
from datetime import datetime
def fixDatetimes(obj):
	if "type" not in obj:
		return obj
	if obj["type"] == "*json-datetime":
		return datetime.utcfromtimestamp(obj["value"])
	return obj

# SETUP: Open data.db
import argparse, json, os, shelve, sys
argumentParser = argparse.ArgumentParser(description="Upgrades txircd's data.db from the 0.4 format to the 0.5 format (Python 3 segment).")
argumentParser.add_argument("--datafile", dest="datafile", help="The location of the data file (default: data.db)", default="data.db")

args = argumentParser.parse_args()

storage = None
os.unlink(args.datafile)
try:
	storage = shelve.open(args.datafile)
except Exception as err:
	print("Error opening data file: {}".format(err))
	sys.exit(1)

# SETUP: Open the json file and put its contents in the storage
with open("{}.json".format(args.datafile), "r") as jsonData:
	data = json.load(jsonData, object_hook=fixDatetimes)

for key, value in data.items():
	storage[key] = value

# SECTION: Upgrade whowas time format and add real host and IP keys
whowasEntries = storage["whowas"]
for whowasEntryList in whowasEntries.values():
	for whowasEntry in whowasEntryList:
		when = whowasEntry["when"]
		whowasEntry["when"] = datetime.utcfromtimestamp(when)
		whowasEntry["realhost"] = whowasEntry["host"]
		whowasEntry["ip"] = "0.0.0.0"

# SHUTDOWN: Close data.db and clean up yaml file
storage.close()
os.unlink("{}.yaml".format(args.datafile))