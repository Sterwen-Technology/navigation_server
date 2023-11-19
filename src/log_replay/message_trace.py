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
import threading

from nmea_routing.configuration import NavigationConfiguration
from nmea_routing.generic_msg import NavGenericMsg, NULL_MSG
from utilities.date_time_utilities import format_timestamp

_logger = logging.getLogger("ShipDataServer." + __name__)


class MessageTraceError(Exception):
    pass


class NMEAMsgTrace:

    (TRACE_IN, TRACE_OUT) = range(1, 3)

    def __init__(self, name, trace_type):
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
        self._trace_fd.write("H0|%s|V1.4\n" % trace_type)
        self._msg_count = 0
        self._trace_lock = threading.Lock()

    def trace(self, direction, msg: NavGenericMsg):
        if self._trace_fd is not None:
            if msg.type == NULL_MSG:
                return
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
        if self._trace_fd is not None:
            _logger.info("Coupler %s closing trace file" % self._name)
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

    def trace_raw(self, direction, msg, strip_suffix=None) -> int:

        """
        Trace a raw (as read unprocessed message or ready to be sent)
        msg is assumed to be bytes or bytearray
        If strip_suffix is not none the corresponding suffix is removed from the message. This is to improve readability
        by removing redundant lf

        Return 0 if no error during decoding or the index after the faulty character if Unicode errors are detected
        """

        if self._trace_fd is not None:
            self._trace_lock.acquire()
            ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            if direction == self.TRACE_IN:
                fc = "R%d#%s>" % (self._msg_count, ts_str)
            else:
                fc = "R%d#%s<" % (self._msg_count, ts_str)
            self._msg_count += 1
            # l = len(msg) - self._separator_len
            # not all messages have the CRLF included to be further checked

            if type(msg) is not str:
                try:
                    msg = msg.decode()
                except UnicodeDecodeError as err:
                    _logger.error("Trace raw on %s error %s on %s" % (self._name, err, msg))
                    self._trace_lock.release()
                    return err.end

            if strip_suffix is not None:
                msg = msg.removesuffix(strip_suffix)

            try:
                self._trace_fd.write(fc)
                self._trace_fd.write(msg)
                self._trace_fd.write('\n')
                self._trace_lock.release()
            except IOError as err:
                _logger.error("Error writing log file: %s" % err)
                self._trace_lock.release()
                raise MessageTraceError
        return 0

    def trace_n2k_raw(self, pgn, sa, prio, data, direction=TRACE_IN):
        if self._trace_fd is not None:
            self._trace_lock.acquire()
            ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            if direction == self.TRACE_IN:
                fc = "N%d#%s>" % (self._msg_count, ts_str)
            else:
                fc = "N#%d%s<" % (self._msg_count, ts_str)
            self._msg_count += 1
            try:
                self._trace_fd.write("%s%06d|%05X|%3d|%d|%s\n" % (fc, pgn, pgn, sa, prio, data.hex()))
                self._trace_lock.release()
            except IOError as err:
                _logger.error("Error writing log file:%s" % err)
                self._trace_lock.release()
                raise MessageTraceError

    def trace_n2k_raw_can(self, time_stamp:datetime.datetime, msg_count, direction, trace_str: str):
        if self._trace_fd is not None:
            self._trace_lock.acquire()
            ts_str = time_stamp.strftime("%Y-%m-%d %H:%M:%S.%f")
            if direction == self.TRACE_IN:
                fc = "R%d#%s>" % (msg_count, ts_str)
            else:
                fc = "R%d#%s<" % (msg_count, ts_str)
            self._msg_count += 1
            # l = len(msg) - self._separator_len
            # not all messages have the CRLF included to be further checked
            try:
                self._trace_fd.write(fc)
                self._trace_fd.write(trace_str)
                self._trace_fd.write('\n')
                self._trace_lock.release()
            except IOError as err:
                _logger.error("Error writing log file: %s" % err)
                self._trace_lock.release()
                raise MessageTraceError

    def add_event_trace(self, message: str):
        if self._trace_fd is not None:
            self._trace_lock.acquire()
            try:
                self._trace_fd.write("Event#>")
                self._trace_fd.write(message)
                self._trace_fd.write('\n')
                self._trace_lock.release()
            except IOError as err:
                _logger.error("Error writing log file: %s" % err)
                self._trace_lock.release()
                raise MessageTraceError

