from twisted.plugin import IPlugin
from txircd.module_interface import IModuleData, ModuleData
from zope.interface import implements
from base64 import b64encode, b64decode
try: # The PBKDF2 module is dumb and reacts different in the presence of PyCrypto, so let's handle its presence appropriately
    from Crypto.Hash import MD55 as md5, SHA as sha1, SHA224 as sha224, SHA256 as sha256, SHA384 as sha384, SHA512 as sha512
except ImportError: # PyCrypto isn't actually present, so let's hashlib
    from hashlib import md5, sha1, sha224, sha256, sha384, sha512
from pbkdf2 import PBKDF2
from random import randint
from struct import pack

class HashPBKDF2(ModuleData):
    implements(IPlugin, IModuleData)
    
    name = "HashPBKDF2"
    
    def hookIRCd(self, ircd):
        self.ircd = ircd
    
    def load(self):
        self.ircd.functionCache["hash-pbkdf2"] = self.hash
    
    def unload(self):
        if self.ircd.functionCache["hash-pbkdf2"] == self.hash:
            del self.ircd.functionCache["hash-pbkdf2"]
    
    def hash(self, string, salt=None, iterations=1000, algorithm="sha256", bytes=24):
        possibleAlgorithms = {
            "md5": md5,
            "sha1": sha1,
            "sha224": sha224,
            "sha256": sha256,
            "sha384": sha384,
            "sha512": sha512
        }
        
        if salt is None:
            salt = self.makeSalt()
        
        if isinstance(salt, unicode):
            salt = salt.encode("us-ascii")
        salt = salt.decode("us-ascii")
        
        if isinstance(string, unicode):
            string = string.encode("utf-8")
        
        if ":" in salt:
            # Here, we're likely comparing against an already computed hash.
            # We need to get the same parameters to make sure that the hash can match.
            # We were given the old hash to pull the parameters out, so let's do that now.
            algorithm, iterations, salt, oldHash = salt.split(":", 3)
            if iterations:
                iterations = int(iterations)
                if iterations < 1:
                    raise ValueError ("Invalid salt")
            bytes = len(b64decode(oldHash))
        
        saltGoodChars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/="
        for char in salt:
            if char not in saltGoodChars:
                raise ValueError ("Illegal character {!r} found in salt".format(char))
        
        if algorithm not in possibleAlgorithms:
            raise ValueError ("Unknown algorithm {}".format(algorithm))
        
        hashedStr = b64encode(PBKDF2(string, salt, iterations, possibleAlgorithms[algorithm]).read(bytes))
        return "{}:{}:{}:{}".format(algorithm, iterations, salt, hash)
    
    def makeSalt(self):
        return b64encode("".join([pack("@H", randint(0, 0xffff)) for i in range(3)]))

pbkdf2Hash = HashPBKDF2()