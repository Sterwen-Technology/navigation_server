#-------------------------------------------------------------------------------
# Name:        serial_nmeaport
# Purpose:     Class manage serial interface for NMEA0183
#
# Author:      Laurent Carré
#
# Created:     15/04/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import serial
import logging

from instrument import Instrument, InstrumentReadError, InstrumentNotPresent, InstrumentTimeOut
from nmea0183 import NMEA0183Msg, NMEAInvalidFrame

_logger = logging.getLogger("ShipDataServer")


class NMEASerialPort(Instrument):

    def __init__(self, opts):
        super().__init__(opts)
        self._separator = b'\r\n'
        self._separator_len = 2
        self._device = opts.get('device', str, None)
        if self._device is None:
            _logger.error("SerialPort %s no device specified" % self.name())
            raise ValueError
        self._baudrate = opts.get('baudrate', int, 4800)
        self._tty = None

    def open(self):

        try:
            self._tty = serial.Serial(self._device, baudrate=self._baudrate, timeout=self._timeout)
        except serial.serialutil.SerialException as e:
            _logger.error("Serial Port %s cannot open TTY:%s" % (self.name(), e))
            return False
        self._state = self.CONNECTED
        return True

    def read(self):

        while True:
            if self._stopflag:
                return NavGenericMsg(NULL_MSG)
            try:
                data = self._tty.readline()
            except serial.serialutil.SerialException as e:
                if not self._stop_flag:
                    _logger.error("Serial Port %s error reading %s" % (self.name(), e))
                    raise InstrumentReadError("Serial Port error")
            if len(data) == 0:
                raise InstrumentTimeOut
            try:
                msg = NMEA0183Msg(data)
            except NMEAInvalidFrame:
                _logger.error("Frame error: %s" % data)
                continue
            break
        if self._trace_msg:
            self.trace(self.TRACE_IN, msg)
        return msg

    def send(self, msg):
        if self._trace_msg:
            self.trace(self.TRACE_OUT, msg)
        try:
            self._tty.write(msg.raw)
        except serial.serialutil.SerialException as e:
            _logger.error("Serial Port %s error writing %s" % (self.name(), e))
            raise InstrumentReadError("Serial Port error")
        return True

    def close(self):
        # super().close()
        self._tty.close()