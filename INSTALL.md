The following steps can be done either directly to the system or in a virtualenv. Make sure to have setuptools up-to-date, as the version of pyopenssl that will be pulled in will not install with an old version of setuptools.

Install dependencies:
    pip install -r requirements.txt

Create a config file in the current directory:
    edit txircd.yaml

Run txircd in the foreground:
    twistd -n txircd
or allow it to daemonise:
    twistd txircd
