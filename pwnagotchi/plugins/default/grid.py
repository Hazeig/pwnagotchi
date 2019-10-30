"""
This plugin signals the unit cryptographic identity and
list of pwned networks and list of pwned networks to api.pwnagotchi.ai
"""
import os
import logging
import time
import glob

from pwnagotchi import grid
from pwnagotchi.utils import StatusFile, WifiInfo, extract_from_pcap
from pwnagotchi.plugins import loaded


__author__ = 'evilsocket@gmail.com'
__version__ = '1.0.1'
__name__ = 'grid'
__license__ = 'GPL3'
__description__ = 'This plugin signals the unit cryptographic identity and list of pwned networks and list of pwned ' \
                  'networks to api.pwnagotchi.ai '


OPTIONS = dict()
PLUGIN = loaded[os.path.basename(__file__).replace(".py","")]


def on_loaded():
    PLUGIN.report = StatusFile('/root/.api-report.json', data_format='json')
    PLUGIN.unread_messages = 0
    PLUGIN.total_messages = 0
    logging.info("grid plugin loaded.")


def parse_pcap(filename):
    logging.info("grid: parsing %s ...", filename)

    net_id = os.path.basename(filename).replace('.pcap', '')

    if '_' in net_id:
        # /root/handshakes/ESSID_BSSID.pcap
        essid, bssid = net_id.split('_')
    else:
        # /root/handshakes/BSSID.pcap
        essid, bssid = '', net_id

    it = iter(bssid)
    bssid = ':'.join([a + b for a, b in zip(it, it)])

    info = {
        WifiInfo.ESSID: essid,
        WifiInfo.BSSID: bssid,
    }

    try:
        info = extract_from_pcap(filename, [WifiInfo.BSSID, WifiInfo.ESSID])
    except Exception as e:
        logging.error("grid: %s", e)

    return info[WifiInfo.ESSID], info[WifiInfo.BSSID]


def is_excluded(what):
    for skip in OPTIONS['exclude']:
        skip = skip.lower()
        what = what.lower()
        if skip in what or skip.replace(':', '') in what:
            return True
    return False


def set_reported(reported, net_id):
    reported.append(net_id)
    PLUGIN.report.update(data={'reported': reported})


def check_inbox(agent):
    logging.debug("checking mailbox ...")

    messages = grid.inbox()
    PLUGIN.total_messages = len(messages)
    PLUGIN.unread_messages = len([m for m in messages if m['seen_at'] is None])

    if PLUGIN.unread_messages:
        logging.debug("[grid] unread:%d total:%d", PLUGIN.unread_messages, PLUGIN.total_messages)
        agent.view().on_unread_messages(PLUGIN.unread_messages, PLUGIN.total_messages)


def check_handshakes(agent):
    logging.debug("checking pcaps")

    pcap_files = glob.glob(os.path.join(agent.config()['bettercap']['handshakes'], "*.pcap"))
    num_networks = len(pcap_files)
    reported = PLUGIN.report.data_field_or('reported', default=list())
    num_reported = len(reported)
    num_new = num_networks - num_reported

    if num_new > 0:
        if OPTIONS['report']:
            logging.info("grid: %d new networks to report", num_new)
            logging.debug("OPTIONS: %s", OPTIONS)
            logging.debug("  exclude: %s", OPTIONS['exclude'])

            for pcap_file in pcap_files:
                net_id = os.path.basename(pcap_file).replace('.pcap', '')
                if net_id not in reported:
                    if is_excluded(net_id):
                        logging.debug("skipping %s due to exclusion filter" % pcap_file)
                        set_reported(reported, net_id)
                        continue

                    essid, bssid = parse_pcap(pcap_file)
                    if bssid:
                        if is_excluded(essid) or is_excluded(bssid):
                            logging.debug("not reporting %s due to exclusion filter", pcap_file)
                            set_reported(reported, net_id)
                        else:
                            if grid.report_ap(essid, bssid):
                                set_reported(reported, net_id)
                            time.sleep(1.5)
                    else:
                        logging.warning("no bssid found?!")
        else:
            logging.debug("grid: reporting disabled")


def on_internet_available(agent):
    logging.debug("internet available")

    try:
        grid.update_data(agent.last_session)
    except Exception as e:
        logging.error("error connecting to the pwngrid-peer service: %s", e)
        logging.debug(e, exc_info=True)
        return

    try:
        check_inbox(agent)
    except Exception as e:
        logging.error("[grid] error while checking inbox: %s", e)
        logging.debug(e, exc_info=True)

    try:
        check_handshakes(agent)
    except Exception as e:
        logging.error("[grid] error while checking pcaps: %s", e)
        logging.debug(e, exc_info=True)
