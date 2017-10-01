Installation instructions
=========================

The following steps can be done either directly to the system or in a virtualenv. Ensure that you're running txircd in a Python 3 environment.

1. Install dependencies:  
`pip install -r requirements.txt`

2. Make txircd visible to be run by twistd:
`pip install -e .`
This command sets up symlinks to the current directory. You only need to run this once.

3. Copy `txircd-example.yaml` to `txircd.yaml`, and edit the configuration. Do the same for included files in the `conf/` directory.

4. Allow txircd to daemonize:  
`twistd txircd`  
or run it in the foreground:  
`twistd -n txircd`  
(If you're running in a virtualenv, start txircd with the twistd in your virtualenv.)
