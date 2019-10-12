__author__ = '33197631+dadav@users.noreply.github.com'
__version__ = '1.0.0'
__name__ = 'bt-tether'
__license__ = 'GPL3'
__description__ = 'This makes the display reachable over bluetooth'

import os
import time
import re
import logging
import subprocess
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
#from pwnagotchi.utils import StatusFile

READY = False
INTERVAL = 0
OPTIONS = dict()


class BluetoothControllerExpection(Exception):
    """
    Just an exception
    """
    pass


class SystemdUnitWrapper:
    """
    systemd wrapper
    """

    def __init__(self, unit):
        self.unit = unit

    @staticmethod
    def _action_on_unit(action, unit):
        process = subprocess.Popen(f"systemctl {action} {unit}", shell=True, stdin=None,
                                  stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
        process.wait()
        if process.returncode > 0:
            return False
        return True

    @staticmethod
    def daemon_reload():
        """
        Calls systemctl daemon-reload
        """
        process = subprocess.Popen("systemctl daemon-reload", shell=True, stdin=None,
                                  stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
        process.wait()
        if process.returncode > 0:
            return False
        return True

    def is_active(self):
        """
        Checks if unit is active
        """
        return SystemdUnitWrapper._action_on_unit('is-active', self.unit)

    def is_enabled(self):
        """
        Checks if unit is enabled
        """
        return SystemdUnitWrapper._action_on_unit('is-enabled', self.unit)

    def is_failed(self):
        """
        Checks if unit is failed
        """
        return SystemdUnitWrapper._action_on_unit('is-failed', self.unit)

    def enable(self):
        """
        Enables the unit
        """
        return SystemdUnitWrapper._action_on_unit('enable', self.unit)

    def disable(self):
        """
        Disables the unit
        """
        return SystemdUnitWrapper._action_on_unit('disable', self.unit)

    def start(self):
        """
        Starts the unit
        """
        return SystemdUnitWrapper._action_on_unit('start', self.unit)

    def stop(self):
        """
        Stops the unit
        """
        return SystemdUnitWrapper._action_on_unit('stop', self.unit)

    def restart(self):
        """
        Restarts the unit
        """
        return SystemdUnitWrapper._action_on_unit('restart', self.unit)


class BluetoothController:
    """
    Wraps bluetoothctl
    """

    PROMPT = '# '

    def __init__(self):
        import pexpect
        self._process = pexpect.spawn("bluetoothctl", echo=False)
        self.run("power on")

    def close(self):
        self._process.close()

    def run(self, cmd, expect_str=None, wait=0):
        """
        Returns the output of the command
        """
        import pexpect
        self._process.sendline(cmd)
        time.sleep(wait)

        if expect_str:
            if self._process.expect([expect_str, 'org.bluez.Error', pexpect.EOF]):
                raise BluetoothControllerExpection("Got an error while running %s" % cmd)
        else:
            self._process.expect_exact(BluetoothController.PROMPT)

        result = self._process.before.decode('utf-8').split("\r\n")
        for line in result:
            if 'org.bluez.Error' in line:
                raise BluetoothControllerExpection(line)

        return result


    def pair(self, mac):
        """
        Attempts to pair with a mac
        """
        try:
            self.run(f"pair {mac}", expect_str="Request confirmation")
            self.run(f"yes", expect_str="Pairing successful")
            return True
        except BluetoothControllerExpection:
            return False

    def connect(self, mac):
        """
        Attempts to pair with a mac
        """
        try:
            self.run(f"connect {mac}", expect_str="Connection successful")
            return True
        except BluetoothControllerExpection:
            return False

    def get_paired(self):
        """
        Get list of paired macs
        """
        result = list()

        for line in self.run('paired-devices'):
            match = re.match(r'Device ((?:[0-9a-fA-F]:?){12}) .*', line)
            if match:
                result.append(match.groups()[0])
        return result

    def look_for(self, mac):
        """
        Look for mac
        """
        try:
            self.run("scan on", expect_str=f"Device {mac}")
            self.run("scan off")
            return True
        except BluetoothControllerExpection:
            return False

    def trust(self, mac):
        """
        Trust the device
        """
        try:
            self.run(f"trust {mac}", expect_str="trust succeeded")
            return True
        except BluetoothControllerExpection:
            return False

    def get_info(self, mac):
        """
        Gets info about device
        """
        info = dict()
        try:
            result = self.run(f"info {mac}")
            for line in result:
                match = re.match(r'[ \t]*([^:]+?):[ \t]*(.+)$', line)
                if match:
                    info[match.groups()[0]] = match.groups()[1]
            return info
        except BluetoothControllerExpection:
            return None

    def is_paired(self, mac):
        """
        Check if mac is paired
        """
        return mac in self.get_paired()

class IfaceWrapper:
    """
    Small wrapper to check and manage ifaces

    see: https://github.com/rlisagor/pynetlinux/blob/master/pynetlinux/ifconfig.py
    """

    def __init__(self, iface):
        self.iface = iface
        self.path = f"/sys/class/net/{iface}"

    def exists(self):
        """
        Checks if iface exists
        """
        return os.path.exists(self.path)

    def is_up(self):
        """
        Checks if iface is ip
        """
        return open(f"{self.path}/operstate", 'r').read().rsplit('\n') == 'up'


    def set_netmask(self, netmask):
        """
        Set the netmask
        """
        import socket, struct, fcntl, math, ctypes
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockfd = sock.fileno()
        netmask = ctypes.c_uint32(~((2 ** (32 - netmask)) - 1)).value
        nmbytes = socket.htonl(netmask)
        ifreq = struct.pack('16sH2sI8s', self.iface.encode(), socket.AF_INET, b'\x00'*2, nmbytes, b'\x00'*8)

        try:
            fcntl.ioctl(sockfd, 0x891C, ifreq)
        except Exception:
            return False
        return True

    def get_netmask(self):
        """
        Get the netmask

        example: 24
        """
        import socket, struct, fcntl, math, ctypes
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockfd = sock.fileno()
        ifreq = struct.pack('16sH14s', self.iface.encode(), socket.AF_INET, b'\x00'*14)
        try:
            res = fcntl.ioctl(sockfd, 0x891B, ifreq)
        except IOError:
            return 0
        netmask = socket.ntohl(struct.unpack('16sH2xI8x', res)[2])

        return 32 - int(round(
            math.log(ctypes.c_uint32(~netmask).value + 1, 2), 1))

    def get_ip(self):
        """
        Get the ipaddr
        """
        import socket, struct, fcntl
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockfd = sock.fileno()
        ifreq = struct.pack('16sH14s', self.iface.encode(), socket.AF_INET, b'\x00'*14)
        try:
            res = fcntl.ioctl(sockfd, 0x8915, ifreq)
        except Exception:
            return None
        ip_addr = struct.unpack('16sH2x4s8x', res)[2]
        return socket.inet_ntoa(ip_addr)


    def set_ip(self, ip):
        """
        Add ip to iface
        """
        import socket, struct, fcntl
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        bin_ip = socket.inet_aton(ip)
        ifreq = struct.pack('16sH2s4s8s', self.iface.encode(), socket.AF_INET, b'\x00' * 2, bin_ip, b'\x00' * 8)
        try:
            fcntl.ioctl(sock, 0x8916, ifreq)
        except Exception:
            return False
        return True


def _ensure_line_in_file(path, regexp, line):
    """
    Emulate ansibles lineinfile
    """
    search_regexp = re.compile(regexp)
    changed = False

    with open(path, 'r') as input_file, open(f"{path}.tmp", 'w') as output_file:
        for old_line in input_file:
            if search_regexp.search(old_line):
                if old_line.rstrip('\n').strip() != line:
                    output_file.write(line + '\n')
                    changed = True
            else:
                output_file.write(old_line)
    if changed:
        process = subprocess.Popen(f"mv {path}.tmp {path}", shell=True, stdin=None,
                                  stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
        process.wait()

        if process.returncode == 0:
            return True

    return False

def on_loaded():
    """
    Gets called when the plugin gets loaded
    """
    global READY

    for opt in ['mac', 'ip', 'netmask', 'interval']:
        if opt not in OPTIONS or (opt in OPTIONS and OPTIONS[opt] is None):
            logging.error("BT-TET: Pleace specify the %s in your config.yml.", opt)
            return

    # ensure bluetooth is running
    bt_unit = SystemdUnitWrapper('bluetooth.service')
    if not bt_unit.is_active():
        if not bt_unit.start():
            logging.error("BT-TET: Can't start bluetooth.service")
            return

    READY = True


def on_ui_update(ui):
    """
    Try to connect to device
    """
    # check check-interval is reached
    global INTERVAL
    if not INTERVAL >= OPTIONS['interval']:
        INTERVAL += 1
        return

    # reset
    INTERVAL = 0

    if READY:
        # Bluetooth should be running by now
        bluetoothctl = BluetoothController()
        # Lets check if bnep0 iface is already there
        btnap_iface = IfaceWrapper('bnep0')
        if not btnap_iface.exists():
            logging.info('BT-TETHER: Iface bnep0 does not exists yet.')
            # not here yet
            # configure & run
            btnap_unit = SystemdUnitWrapper('btnap.service')

            # lets put our mac into the config
            _ensure_line_in_file('/etc/btnap.conf', r'^REMOTE_DEV=', f"REMOTE_DEV=\"{OPTIONS['mac']}\"")

            logging.info("BT-TETHER: Look if %s is around", OPTIONS['mac'])
            ui.set('bt', 'S?')
            ui.update(force=True)
            if bluetoothctl.look_for(OPTIONS['mac']):
                ui.set('bt', 'S!')
                ui.update(force=True)
                logging.info('BT-TETHER: Try to restart btnap.service.')
                if not btnap_unit.restart():
                    logging.error('BT-TETHER: Restart failed')
                    bluetoothctl.close()
                    return # fck, cant restart

        # bnep0 should be there by now
        if btnap_iface.exists():
            # check ip
            if btnap_iface.get_ip() != OPTIONS['ip']:
                logging.info("BT-TETHER: Set ip of bnep0 to %s", OPTIONS['ip'])
                btnap_iface.set_ip(OPTIONS['ip'])

            # check netmask
            if btnap_iface.get_netmask() != OPTIONS['netmask']:
                logging.info("BT-TETHER: Set netmask of bnep0 to %s", OPTIONS['netmask'])
                btnap_iface.set_netmask(OPTIONS['netmask'])
        else:
            logging.error('BT-TETHER: bnep0 still not here ...')
            bluetoothctl.close()
            return

        if not bluetoothctl.is_paired(OPTIONS['mac']):
            logging.info("BT-TETHER: Look if %s is around", OPTIONS['mac'])
            ui.set('bt', 'S?')
            ui.update(force=True)
            if bluetoothctl.look_for(OPTIONS['mac']):
                ui.set('bt', 'P?')
                ui.update(force=True)
                logging.info("BT-TETHER: Trying to pair to %s", OPTIONS['mac'])
                if bluetoothctl.pair(OPTIONS['mac']):
                    ui.set('bt', 'T?')
                    ui.update(force=True)
                    logging.info("BT-TETHER: Trying to trust %s", OPTIONS['mac'])
                    if bluetoothctl.trust(OPTIONS['mac']):
                        logging.info("BT-TETHER: Successful trusted  %s", OPTIONS['mac'])
                        ui.set('bt', 'T!')
                        ui.update(force=True)
        else:
            info = bluetoothctl.get_info(OPTIONS['mac'])
            if info:
                if info['Trusted'] == 'no':
                    logging.info("BT-TETHER: Trying to trust %s", OPTIONS['mac'])
                    ui.set('bt', 'T?')
                    ui.update(force=True)
                    if bluetoothctl.trust(OPTIONS['mac']):
                        logging.info("BT-TETHER: Successful trusted  %s", OPTIONS['mac'])
                        ui.set('bt', 'T!')
                        ui.update(force=True)

                elif info['Connected'] == 'no':
                    ui.set('bt', 'S?')
                    ui.update(force=True)
                    logging.info("BT-TETHER: Look if %s is around", OPTIONS['mac'])
                    if bluetoothctl.look_for(OPTIONS['mac']):
                        logging.info("BT-TETHER: Trying to connect to %s", OPTIONS['mac'])
                        ui.set('bt', 'C?')
                        ui.update(force=True)
                        if bluetoothctl.connect(OPTIONS['mac']):
                            logging.info("BT-TETHER: Successful connected to %s", OPTIONS['mac'])
                            ui.set('bt', 'C!')
                            ui.update(force=True)


        bluetoothctl.close()


def on_ui_setup(ui):
    ui.add_element('bt', LabeledValue(color=BLACK, label='BT', value='-', position=(ui.width() / 2 - 25, 0),
                                       label_font=fonts.Bold, text_font=fonts.Medium))
