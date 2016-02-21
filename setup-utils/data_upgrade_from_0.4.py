# This file upgrades data.db from the 0.4 format data to 0.5 format data.

# SETUP: Open data.db
import argparse, shelve, sys
argumentParser = argparse.ArgumentParser(description="Upgrades txircd's data.db from the 0.4 format to the 0.5 format.")
argumentParser.add_argument("--datafile", dest="datafile", help="The location of the data file (default: data.db)", default="data.db")

args = argumentParser.parse_args()

storage = None
try:
	storage = shelve.open(args.datafile)
except Exception as err:
	print("Error opening data file: {}".format(err))
	sys.exit(1)

# SECTION: Upgrade whowas time format
from datetime import datetime
whowasEntries = storage["whowas"]
for whowasEntryList in whowasEntries.itervalues():
	for whowasEntry in whowasEntryList:
		when = whowasEntry["when"]
		whowasEntry["when"] = datetime.utcfromtimestamp(when)

# SHUTDOWN: Close data.db
storage.close()