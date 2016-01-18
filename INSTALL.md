Installation instructions
=========================

The following steps can be done either directly to the system or in a virtualenv.

1. Install dependencies:  
`pip install -r requirements.txt`

2. Copy `txircd-example.yaml` to `txircd.yaml`, and edit the configuration. Do the same for included files in the `conf/` directory.

3. Allow txircd to deamonize:  
`twistd txircd`  
or run it in the foreground:  
`twistd -n txircd`  
(If you're running in a virtualenv, start txircd with the twistd in your virtualenv.)
