# -------------------------------------------------------------------------------
# Name:        modem_command
# Purpose:     Perform direct commands to yje modem via the modem_lib
#
# Author:      Laurent Carré
#
# Created:     11/04/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2020-2025
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import sys
import json
import datetime
import time
from argparse import ArgumentParser

from navigation_server.network import *

log = logging.getLogger('ShipDataServer.' + __name__)


def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument('-R', '--reset', action='store_true', help="Perform a soft reset of the modem")
    p.add_argument('-gps', '--gps', action='store_true', help="Display/send GPS status - turn it on")
    p.add_argument('-gps_off', '--gps_off', action='store_true', help="Turn the GPS off")
    p.add_argument('-v', '--verbose', action='store_true', help="Verbose mode")
    p.add_argument('-d', '--detect', action='store_true', help="Detect the modem, shall be run once")
    p.add_argument('-c', '--cmd', action='store', default=None, help="Send a AT command to the modem")
    p.add_argument('-w', '--wait', action='store', type=float, default=0.0, help="Wait time in sec when needed")
    p.add_argument('-p', '--pin', action='store', help="PIN code to unlock the SIM card")
    p.add_argument('-l', '--list', action='store_true', help="List all visible operators and technology")
    p.add_argument('-to', '--sms_to', action='store', help="Number(MSISDN) address for SMS")
    p.add_argument('-t', '--text', action='store', help="Text of the SMS")
    p.add_argument('-sms', '--sms', action='store_true')
    p.add_argument('-i', '--init', action='store_true', help="Send default configuration to modem")
    p.add_argument('-del', '--delete_sms', action='store_true', help="Delete SMS after reading")
    p.add_argument('-r', '--read_sms', action='store', choices=['all', 'unread'], default=None,
                   help="Read SMS")
    p.add_argument('-log_at', '--log_at', action='store_true', help="Log all low level exchanges with the modem")
    p.add_argument('-rescan', '--rescan', action='store_true', help='Start scanning for operator')
    p.add_argument('-dir', '--dir', action="store", default=None, help="Directory for modem configuration file")

    return p


def checkSMS(modem):
    resp = modem.sendATcommand("+CSMS?")
    s = modem.splitResponse("+CSMS", resp[0])
    log.info("SMS service type: " + str(s[0]) + " MO:" + str(s[1]) + " MT:" + str(s[2]) + " BM:" + str(s[3]))
    resp = modem.sendATcommand("+CSCA?")
    s = modem.splitResponse("+CSCA", resp[0])
    log.info("SMS Service center:" + str(s[0]))


def init_modem(modem):
    modem.clearFPLMN()
    modem.allowRoaming()
    modem.configureSMS()


def rescan(modem):
    log.info("Resetting network scan mode")
    modem.sendATcommand('+QCFG=”nwscanmode”,0,1')
    modem.selectOperator('AUTO')


def checkGPS(modem):
    if modem.gpsStatus():
        log.info("Reading GPS")
        sg = modem.getGpsStatus()
        if sg['fix']:
            latitude = float(sg['latitude'][:-1]) / 100.
            if sg['latitude'][-1] == 'S':
                latitude = -latitude
            longitude = float(sg['longitude'][:-1]) / 100.
            if sg['longitude'][-1] == 'W':
                longitude = -longitude
            pf = f"GPS latitude {latitude} longitude {longitude} date {sg['date']} time {sg['time_UTC']}"
            print(pf)
        else:
            log.info("GPS not fixed")
    else:
        log.info("GPS is turned off => turning on")
        modem.gpsOn()


sms_stat = {'all': 'ALL',
            'unread': 'REC UNREAD'
            }


def read_sms(modem, stat, delete):
    stat = sms_stat.get(stat, None)
    if stat is None:
        print("Incorrect SMS read command")
    else:
        messages = modem.readSMS(stat)
        for msg in messages:
            end = msg['sms_time'].rfind("+")
            if end < 6:
                continue
            timestamp = datetime.datetime.strptime(msg['sms_time'][:end], '%y/%m/%d,%H:%M:%S')
            print(f"From:{msg['origin']} at:{timestamp}: {msg['text']}")
        if delete:
            modem.deleteSMS()



def main():
    parser = _parser()
    opts = parser.parse_args()

    log.addHandler(logging.StreamHandler())
    if opts.verbose:
        log.setLevel(logging.INFO)
    else:
        log.setLevel(logging.WARNING)
    if opts.detect:
        print("Detection of the modem...")
        try:
            modem_def = QuectelModem.checkModemPresence(opts)
        except ModemException as err:
            print(f"Error during modem detection {err}")
            return 2
        print(f"Modem type {modem_def['model']} found with control tty {modem_def['tty_list'][2].tty_name}")

    try:
        modem = QuectelModem(0, log=opts.log_at, filepath=opts.dir)
    except Exception as err:
        log.error(str(err))
        return 2

    if opts.reset:
        print("Performing soft reset on modem")
        modem.resetCard()
        print("Soft reset done - the modem is not ready")
        if opts.wait > 0:
            print(f"Waiting {opts.wait} seconds")
            time.sleep(opts.wait)
        else:
            return

    if opts.init:
        # re-init of modem parameters
        print("Initializing modem (Forbidden PLMN, roaming and SMS)")
        init_modem(modem)

    if opts.gps:
        checkGPS(modem)
    elif opts.gps_off:
        modem.gpsOff()

    if not modem.checkSIM(opts.pin):
        log.error("No SIM card inserted or incorrect PIN code")
        return 1
    print(f"Modem and SIM card ready IMSI {modem.IMSI}, ICC-ID {modem.ICCID}")
    # read the operators name file
    modem.read_operators_names()
    # now we need to check the network status, or we just look for networks
    if opts.list:
        result = modem.visibleOperators()
        jresult = json.dumps(result, indent=2)
        print(jresult)
        return 0
    elif opts.rescan:
        rescan(modem)
        return 0
    elif not modem.networkStatus():
        print(f"The modem is not attached to the network status {modem.regStatus()}")
        if modem.regStatus() == "IN PROGRESS" and opts.wait > 0:
            start_time = time.time()
            current_time = start_time
            print(f"Waiting {opts.wait} seconds for attachment")
            while (current_time - start_time) < opts.wait:
                sys.stderr.write("..")
                time.sleep(1.0)
                if modem.networkStatus():
                    sys.stderr.write("\n")
                    break
                current_time = time.time()
            if modem.regStatus() != "READY":
                return 1
    #
    # SMS section
    #
    if opts.sms:
        checkSMS(modem)
    if opts.sms_to is not None:
        modem.check_sms_mode()
        if opts.text is None:
            log.error("No text for the SMS")
        else:
            resp = modem.sendSMS(opts.sms_to, opts.text)
            if resp == "OK":
                print("SMS sent")

    if opts.read_sms is not None:
        read_sms(modem, opts.read_sms, opts.delete_sms)

    if opts.cmd is not None:
        # that is rudimentary
        resp = modem.sendATcommand(opts.cmd, raiseException=True)
        print(resp)

    modem.close()
    return 0


if __name__ == '__main__':
    exit_val = main()
    if exit_val is None:
        exit_val = 0
    exit(exit_val)
