import sys
sys.path.append("..") # This needs to work from the setup-utils subdirectory
from txircd.modules.hash_pbkdf2 import HashPBKDF2

if len(sys.argv) < 2:
	print("Usage: {} password".format(__file__))
else:
	hasher = HashPBKDF2()
	hashedPass = hasher.hash(sys.argv[1])
	print(hashedPass)