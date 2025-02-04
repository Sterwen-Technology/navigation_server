#-------------------------------------------------------------------------------
# Name:        Internal GPS
# Purpose:     Class to access the SolidSEnse internal Quectel GPS
#
# Author:      Laurent Carré
#
# Created:     29/11/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import serial
import logging
import json
import time
import threading


_logger = logging.getLogger("ShipDataServer."+__name__)


from navigation_server.network import QuectelModem
from navigation_server.router_core import Coupler, CouplerReadError, CouplerNotPresent, NMEA0183Msg, NMEAInvalidFrame


class InternalGps(Coupler):

    def __init__(self, opts):

        super().__init__(opts)
        _logger.debug("Internal GPS coupler - connecting to Quectel modem")
        self._separator = b'\r\n'
        self._separator_len = 2
        fp = open("/data/solidsense/modem_gps/parameters.json")
        self._params = json.load(fp)
        fp.close()
        _logger.debug("modem control file:%s" % self._params['modem_ctrl'])
        self._modem = QuectelModem(self._params['modem_ctrl'])
        status = self._modem.getGpsStatus()
        _logger.info("Internal GPS status:%s" % status)
        if status['state'] == 'off':
            self._modem.gpsOn()
            time.sleep(0.4)
            status = self._modem.getGpsStatus()
            _logger.info("Internal GPS status after GPS on:%s", status)

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
        _logger.info("Internal GPS interface:%s ready", self._nmea_if)
        self._modem.close()

    def open(self):
        try:
            self._tty = serial.Serial(self._nmea_if, baudrate=9600, timeout=10.)
        except (serial.serialutil.SerialException, BrokenPipeError) as e:
            _logger.error("Internal GPS cannot open TTY %s :%s" % (self._nmea_if, str(e)))
            return False
        self._state = self.CONNECTED
        return True

    def _read(self):
        self._fix_event.wait()
        if self._stopflag:
            return None
        if self._fix:
            _logger.debug("GPS read => fix OK")
            try:
                data = self._tty.readline()
            except serial.serialutil.SerialException as e_read:
                _logger.error("Internal GPS error reading %s" % str(e_read))
                raise CouplerReadError("Serial error")
            data = data.rstrip(b'\r\n')  # sometimes <CR> is duplicated
            try:
                msg = NMEA0183Msg(data)
            except NMEAInvalidFrame:
                _logger.error("GPS read invalid frame:%s" % data)
                raise CouplerReadError("Frame error")

            self.trace_raw(self.TRACE_IN, data, '\r\n')
            if self._talker is not None:
                msg.replace_talker(self._talker)
            return msg

    def close(self):
        self._state = self.NOT_READY
        if self._tty is not None:
            self._tty.close()
        self._fix_event.set()

    def timer_lapse(self):
        self._modem.open()
        status = self._modem.getGpsStatus()
        fix = status['fix']
        self._modem.close()
        _logger.debug("Internal GPS check fix %r" % fix)
        if not self._fix and fix:
            _logger.info("Internal GPS become fixed")
            self._fix = True
            self._fix_event.set()
        elif self._fix and not fix:
            self._fix_event.clear()
            self._fix = False
            _logger.info("Internal GPS lost fix")
        super().timer_lapse()

    def send(self):
        pass
