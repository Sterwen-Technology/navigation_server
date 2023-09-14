# -------------------------------------------------------------------------------
# Name:        NMEA2K-CAN Interface class
# Purpose:     Implements the direct CAN Bus interface
#
# Author:      Laurent Carré
#
# Created:     12/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import datetime
import logging
import os

from nmea_routing.configuration import NavigationConfiguration
from nmea_routing.generic_msg import NavGenericMsg
from utilities.date_time_utilities import format_timestamp

_logger = logging.getLogger("ShipDataServer." + __name__)


class MessageTraceError(Exception):
    pass


class NMEAMsgTrace:

    (TRACE_IN, TRACE_OUT) = range(1, 3)

    def __init__(self, name, default_on=True, raw=True):
        self._name = name
        trace_dir = NavigationConfiguration.get_conf().get_option('trace_dir', '/var/log')
        date_stamp = datetime.datetime.now().strftime("%y%m%d-%H%M")
        filename = "TRACE-%s-%s.log" % (name, date_stamp)
        filepath = os.path.join(trace_dir, filename)
        _logger.info("Opening trace file %s" % filepath)
        try:
            self._trace_fd = open(filepath, "w")
        except IOError as e:
            _logger.error("Trace file error %s" % e)
            raise MessageTraceError
        self._trace_fd.write("H0|%s|V1.4\n" % type(self))
        self._trace_msg = default_on
        self._trace_raw = raw
        self._msg_count = 0

    def trace(self, direction, msg: NavGenericMsg):
        if self._trace_msg:
            ts_str = format_timestamp(msg.msg.timestamp, "%Y-%m-%d %H:%M:%S.%f")
            if direction == self.TRACE_IN:
                fc = "M%d#%s>" % (self._msg_count, ts_str)
            else:
                fc = "M%d#%s<" % (self._msg_count, ts_str)
            self._msg_count += 1
            self._trace_fd.write(fc)
            out_msg = msg.printable()
            self._trace_fd.write(out_msg)
            self._trace_fd.write('\n')

    def stop_trace(self):
        if self._trace_msg or self._trace_raw:
            _logger.info("Coupler %s closing trace file" % self._name)
            self._trace_msg = False
            self._trace_raw = False
            self._trace_fd.close()
            self._trace_fd = None
        else:
            _logger.error("Coupler %s attempt closing inactive trace" % self._name)

    '''
    def start_trace_raw(self):
        if not self.is_alive():
            _logger.error("Coupler %s attempt to start traces while not running")
            return
        _logger.info("Starting traces on raw input on %s" % self.name())
        if self.open_trace_file():
            self._trace_raw = True
    '''

    def trace_raw(self, direction, msg):
        if self._trace_raw:
            # ts = datetime.datetime.now()
            ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            if direction == self.TRACE_IN:
                fc = "R%d#%s>" % (self._msg_count, ts_str)
            else:
                fc = "R%d#%s<" % (self._msg_count, ts_str)
            self._msg_count += 1
            # l = len(msg) - self._separator_len
            # not all messages have the CRLF included to be further checked
            try:
                self._trace_fd.write(fc)
                if not type(msg) == str:
                    msg = msg.decode()
                self._trace_fd.write(msg)
                self._trace_fd.write('\n')
            except IOError as err:
                if self._trace_raw:
                    _logger.error("Error writing log file: %s" % err)
                    self._trace_raw = False

    def trace_n2k_raw(self, pgn, sa, prio, data, direction=TRACE_IN):
        if self._trace_msg and self._trace_raw:
            if direction == self.TRACE_IN:
                fc = "N%d#>" % self._msg_count
            else:
                fc = "N#%d<" % self._msg_count
            self._msg_count += 1
            self._trace_fd.write("%s%06d|%05X|%3d|%d|%s\n" % (fc, pgn, pgn, sa, prio, data.hex()))

    def add_event_trace(self, message: str):
        if self._trace_msg:
            self._trace_fd.write("Event#>")
            self._trace_fd.write(message)
            self._trace_fd.write('\n')

