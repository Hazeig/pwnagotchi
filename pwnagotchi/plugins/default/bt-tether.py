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

    PROMPT = '\x1b[0;94m[bluetooth]\x1b[0m# '

    def __init__(self):
        import pexpect
        self._process = pexpect.spawn("bluetoothctl", echo=False)
        self.run("power on")


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

    if 'mac' not in OPTIONS or ('mac' in OPTIONS and OPTIONS['mac'] is None):
        logging.error("BT-TET: Pleace specify the mac of the bluetooth device.")
        return

    bt_unit = SystemdUnitWrapper('bluetooth.service')
    btnap_unit = SystemdUnitWrapper('btnap.service')

    if _ensure_line_in_file('/etc/btnap.conf', r'^REMOTE_DEV=', f"REMOTE_DEV={OPTIONS['mac']}"):
        if not btnap_unit.restart():
            logging.error("BT-TET: Can't restart btnap.service")
            return

    if not bt_unit.is_active():
        if not bt_unit.start():
            logging.error("BT-TET: Can't start bluetooth.service")
            return

    if not btnap_unit.is_active():
        if btnap_unit.start():
            logging.error("BT-TET: Can't start btnap.service")
            return

    READY = True


def on_epoch(agent, epoch, epoch_data):
    """
    Try to connect to device
    """
    if READY:
        ui = agent.view()
        bluetoothctl = BluetoothController()
        if not bluetoothctl.is_paired(OPTIONS['mac']):
            ui.set('bt', 'S?')
            ui.update(force=True)
            if bluetoothctl.look_for(OPTIONS['mac']):
                ui.set('bt', 'P?')
                ui.update(force=True)
                if bluetoothctl.pair(OPTIONS['mac']):
                    ui.set('bt', 'T?')
                    ui.update(force=True)
                    if bluetoothctl.trust(OPTIONS['mac']):
                        ui.set('bt', 'T!')
                        ui.update(force=True)
        else:
            info = bluetoothctl.get_info(OPTIONS['mac'])
            if info:
                if info['Trusted'] == 'no':
                    ui.set('bt', 'T?')
                    ui.update(force=True)
                    if bluetoothctl.trust(OPTIONS['mac']):
                        ui.set('bt', 'T!')
                        ui.update(force=True)

                elif info['Connected'] == 'no':
                    ui.set('bt', 'S?')
                    ui.update(force=True)
                    if bluetoothctl.look_for(OPTIONS['mac']):
                        ui.set('bt', 'C?')
                        ui.update(force=True)
                        if bluetoothctl.connect(OPTIONS['mac']):
                            ui.set('bt', 'C!')
                            ui.update(force=True)


def on_ui_setup(ui):
    ui.add_element('bt', LabeledValue(color=BLACK, label='BT', value='-', position=(ui.width() / 2 - 25, 0),
                                       label_font=fonts.Bold, text_font=fonts.Medium))
