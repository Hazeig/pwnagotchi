## gps

info      | data
----------|-----------------------
author    | evilsocket@gmail.com
version   | 1.0.0
license   | GPL3

### changelog

version   | changes
----------|----------
1.0.0     | initial release

### options

name      | description              | default      |required
----------|--------------------------|--------------|---------
device    | Path to the gps device   | /dev/ttyUSB0 |  x
speed     | Speed of the gps device  | 19200        |  x

### description

This plugin will save the gps-position for every handshake you capture. The saved gps
position can be used to plot it on a map, contribute to other wifi related projects,
or simply to have some information about the wifi location, in case you cracked the
password and want to tell the wifi owner how bad his password is ;).
