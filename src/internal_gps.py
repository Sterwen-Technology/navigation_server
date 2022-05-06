#-------------------------------------------------------------------------------
# Name:        Internal GPS
# Purpose:     Class to access the SolidSEnse internal Quectel GPS
#
# Author:      Laurent Carré
#
# Created:     29/11/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import serial
import logging
import json
import sys
import time
import threading

sys.path.insert(0, "/opt/SolidSense/modem_gps")
_logger = logging.getLogger("ShipDataServer")

try:
    from QuectelAT_Service import *
    gps_present = True
except ImportError as e:
    _logger.error(str(e))
    gps_present = False

from instrument import Instrument, InstrumentReadError, InstrumentNotPresent
from nmea0183 import NMEA0183Msg


class InternalGps(Instrument):

    def __init__(self, opts):

        if not gps_present:
            raise InstrumentNotPresent('InternalGPS')

        super().__init__(opts)
        self._separator = b'\r\n'
        self._separator_len = 2
        fp = open("/data/solidsense/modem_gps/parameters.json")
        self._params = json.load(fp)
        fp.close()
        self._modem = QuectelModem(self._params['modem_ctrl'])
        status = self._modem.getGpsStatus()
        # print(status)
        if status['state'] == 'off':
            self._modem.gpsOn()
            time.sleep(0.4)
            status = self._modem.getGpsStatus()
            print(status)

        self._nmea_if = self._params['nmea_tty']
        self._tty = None
        self._fix = status['fix']
        self._fix_event = threading.Event()
        if self._fix:
            _logger.info("Internal GPS fixed")
            self._fix_event.set()
        else:
            self._fix_event.clear()
            _logger.info("Internal GPS NOT fixed")
        _logger.info("Internal GPS interface:%s", self._nmea_if)
        self._modem.close()

    def open(self):
        try:
            self._tty = serial.Serial(self._nmea_if, baudrate=9600, timeout=10.)
        except serial.serialutil.SerialException as e:
            _logger.error("Internal GPS cannot open TTY:%s"% str(e))
            return False
        self._state = self.CONNECTED
        return True

    def read(self):
        self._fix_event.wait()
        if self._stopflag:
            return None
        if self._fix:
            try:
                data = self._tty.readline()
            except serial.serialutil.SerialException as e:
                _logger.error("Internal GPS error reading %s" % str(e))
                raise InstrumentReadError("Serial error")
            msg = NMEA0183Msg(data)
            self.trace(self.TRACE_IN, msg)
            if self._talker is not None:
                msg.replace_talker(self._talker)
            return msg

    def close(self):
        self._state = self.NOT_READY
        self._tty.close()
        self._fix_event.set()

    def timer_lapse(self):
        self._modem.open()
        status = self._modem.getGpsStatus()
        fix = status['fix']
        self._modem.close()
        if not self._fix and fix:
            _logger.info("Internal GPS become fixed")
            self._fix = True
            self._fix_event.set()
        elif self._fix and not fix:
            self._fix_event.clear()
            _logger.info("Internal GPS lost fix")
        super().timer_lapse()

    def send(self):
        pass
