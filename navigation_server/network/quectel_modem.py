# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:        Quectel modem manager
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     26/06/2019
# Copyright:   (c) Laurent Carré Sterwen Technologies 2019-2025
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------


import logging
import time

from .usb_modem_at_lib import *

modem_log = logging.getLogger('ShipDataServer.' + __name__)


class QuectelModem(UsbATModem):

    @staticmethod
    def checkModemPresence(opts, save_modem=True):
        return UsbATModem.checkModemPresence(opts, 'Quectel', save_modem)

    def __init__(self, if_num=0, log=False, * , init=True, filepath=None):

        super().__init__(if_num, log, init=init, filepath=filepath)
        self._manufacturer = 'Quectel'
        r = self.sendATcommand("I")
        if r[0] != self.manufacturer():
            # print "Wrong manufacturer:",r
            raise ModemException("Wrong manufacturer:" + str(r))
        self._model = r[1]
        self._rev = r[2]

    def _checkSIM(self) -> bool:
        # check if SIM is present
        modem_log.debug("Checking SIM status")
        r = self.sendATcommand("+QSIMSTAT?")
        sim_status_read = False
        sim_flags = None
        sim_lock = None
        for resp in r:
            cmd = self.checkResponse(resp)
            if cmd == "+QSIMSTAT":
                sim_flags = self.splitResponse("+QSIMSTAT", resp)
            elif cmd == "+CPIN":
                sim_lock = self.splitResponse("+CPIN", resp)
                sim_status_read = True

        # print("SIM FLAGS=",sim_flags)
        if sim_flags is not None and sim_flags[1] == 1:
            # there is a SIM inserted
            modem_log.debug("SIM inserted locked %s" % sim_lock)
            self._SIM = True
            if not sim_status_read:
                r = self.sendATcommand("+CPIN?")
                sim_lock = self.splitResponse("+CPIN", r[0])
            # print("SIM lock=",sim_lock[0])
            if sim_lock is not None:
                self._SIM_STATUS = sim_lock[0]
                if sim_lock[0] == "READY":
                    r = self.sendATcommand("+CIMI")
                    self._IMSI = r[0]
                    if self._stored_imsi != self._IMSI:
                        modem_log.warning("SIM card has been changed)")
                        self._sim_change_flag = True
                        self._stored_imsi = self._IMSI
                        self._store_def()
                    r = self.sendATcommand("+QCCID")
                    r = self.splitResponse("+QCCID", r[0])
                    # on ICCID, the last byte shall be left out
                    modem_log.debug(f"Read ICCID result{r[0]}")
                    # discard the 2 low digits (CRC)
                    # correction 2025-01-02 QCCID is a string with 2 supplémentary characters
                    # but can also be an int depending on the SIM card
                    # was corrected on the fly or the system on Swann
                    # print(f"QICCD={r[0]} type {type(r[0])}")
                    if type(r[0]) is int:
                        qiccid_str = str(r[0])
                    else:
                        qiccid_str = r[0]
                    if len(qiccid_str) > 18:
                        self._ICCID = qiccid_str[:18]
                    else:
                        self._ICCID = qiccid_str
                    # print(f"QCCID {r[0]} ICCID {self._ICCID}")
                    # self._ICCID = int(r[0] // 100)
                    # print("ICCID:",self._ICCID,"Type:",type(self._ICCID))
                    # allow full notifications on registration change
                    self.sendATcommand("+CREG=2")
            return True
        else:
            self._SIM = False
            return False

    def _get_operator_name(self):

        resp = self.sendATcommand("+QSPN")
        param = self.checkAndSplitResponse("+QSPN", resp)
        if param is not None:
            self._networkName = param[0]
            self._regPLMN = param[4]
        else:
            self._networkName = "Unknown"
            self._regPLMN = 0

        self._isRegistered = True
        #
        # Get quality indicators
        #
        # print("Decoding network info")
        resp = self.sendATcommand("+QNWINFO")
        param = self.checkAndSplitResponse("+QNWINFO", resp)
        if param is not None:
            self._decodeNetworkInfo(param)
        else:
            modem_log.error("Error on network info")
            raise ModemException()

    def factoryDefault(self):
        modem_log.info("RESTORING FACTORY DEFAULT")
        self.sendATcommand("+QPRTPARA=3")
        time.sleep(1.0)
        modem_log.info("RESETTING THE MODEM")
        self.sendATcommand("+CFUN=1,1")
        self.close()
        modem_log.info("Allow 20-30 sec for the modem to restart")

        #
        # turn GPS on with output on ttyUSB1 as NMEA sentence
        #

    def gpsOn(self):
        """
        Turn GPS on
        :return:
        :rtype:
        """
        resp = self.sendATcommand("+QGPSCFG=\"outport\",\"usbnmea\"", True)
        resp = self.sendATcommand("+QGPSCFG=\"autogps\",1", True)
        resp = self.sendATcommand("+QGPS=1", True)

    def gpsOff(self):
        resp = self.sendATcommand("+QGPSEND", True)
        resp = self.sendATcommand("+QGPSCFG=\"autogps\",0", True)

    def getGpsStatus(self) -> dict:
        """
        Reads the full GPS status from the modem and returns all parameters in a dictionary
        :return:
        :rtype:
        """
        status = {}
        if not self.gpsStatus():
            status['state'] = 'off'
            return status
        #
        # now the GPS is on let's see what have
        #
        status['state'] = 'on'
        # modem_log.debug("GPS is ON")
        #
        # check NMEA port
        #
        # modem_log.debug("Reading NMEA port parameters")
        resp = self.sendATcommand("+QGPSCFG=\"outport\"")
        param = self.checkAndSplitResponse("+QGPSCFG", resp)
        status["NMEA_port1"] = param[0]
        status['NMEA_port2'] = param[1]
        # read values
        # modem_log.debug("Reading GPS via AT")
        resp = self.sendATcommand("+QGPSLOC=0", False)
        # print("GPS RESP=",resp)
        # check that we are fixed
        cmd = self.checkResponse(resp[0])
        if cmd.startswith('+CME'):
            err = int(self.splitResponse("+CME ERROR", resp[0])[0])
            # print("ERROR=",err)
            if err == 516:
                status['fix'] = False
            else:
                status['fix'] = err
            return status
        # now we shall have a valid GPS signal

        param = self.checkAndSplitResponse("+QGPSLOC", resp)
        if param is None:
            status['fix'] = False
        else:
            status['fix'] = True
            status["time_UTC"] = param[0]
            status["latitude"] = param[1]
            status['longitude'] = param[2]
            status['hdop'] = param[3]
            status['Altitude'] = param[4]
            status['date'] = param[9]
            status["nbsat"] = param[10]
            status["SOG_KMH"] = param[8]
        return status

    def gpsStatus(self):
        resp = self.sendATcommand("+QGPS?")
        param = self.checkAndSplitResponse("+QGPS", resp)
        if param is None:
            return False
        if param[0] == 0:
            return False
        else:
            return True

    def gpsPort(self):
        resp = self.sendATcommand("+QGPSCFG=\"outport\"")
        param = self.checkAndSplitResponse("+QGPSCFG", resp)
        return param[1]
