#-------------------------------------------------------------------------------
# Name:        Coupler
# Purpose:     Abstract super class for all instruments
#
# Author:      Laurent Carré
#
# Created:     29/11/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import datetime
import os
import socket


import threading
import logging
import time
# from publisher import Publisher
from nmea_routing.configuration import NavigationConfiguration
from nmea_routing.publisher import PublisherOverflow
from nmea_routing.generic_msg import NavGenericMsg, NULL_MSG, N2K_MSG
from nmea_routing.nmea2000_msg import NMEA2000Msg, NMEA2000Writer


_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class CouplerReadError(Exception):
    pass


class CouplerTimeOut(CouplerReadError):
    pass


class CouplerNotPresent(Exception):
    pass


class Coupler(threading.Thread):
    '''
    Base abstract class for all instruments
    '''

    (NOT_READY, OPEN, CONNECTED, ACTIVE) = range(4)
    (BIDIRECTIONAL, READ_ONLY, WRITE_ONLY) = range(10, 13)
    (NMEA0183, NMEA2000, NMEA_MIX) = range(20, 23)
    (TRACE_IN, TRACE_OUT) = range(30, 32)

    dir_dict = {'bidirectional': BIDIRECTIONAL,
                'read_only': READ_ONLY,
                'write_only': WRITE_ONLY}

    protocol_dict = {'nmea0183': NMEA0183, 'nmea2000': NMEA2000, 'nmea_mix': NMEA_MIX}

    def __init__(self, opts):
        name = opts['name']
        super().__init__(name=name)
        self._name = name
        self._opts = opts
        self._publishers = []
        self._configmode = False
        self._configpub = None
        self._startTS = 0
        self._total_msg = 0
        self._total_msg_s = 0
        self._last_msg_count = 0
        self._last_msg_count_s = 0
        self._report_timer = opts.get('report_timer', float,  30.0)
        self._timeout = opts.get('timeout', float, 10.0)
        self._max_attempt = opts.get('max_attempt', int, 20)
        self._open_delay = opts.get('open_delay', float, 2.0)
        self._autostart = opts.get('autostart', bool, True)
        self._talker = opts.get('talker', str, None)
        if self._talker is not None:
            self._talker = self._talker.upper().encode()
        direction = opts.get('direction', str, 'bidirectional')
        # print(self.name(), ":", direction)
        self._direction = self.dir_dict.get(direction, self.BIDIRECTIONAL)
        mode = opts.get('protocol', str, 'nmea0183')
        self._mode = self.protocol_dict[mode.lower()]
        _logger.info("Coupler %s mode %d direction %d" % (self._name, self._mode ,self._direction))
        if self._mode == self.NMEA2000 and self._direction != self.READ_ONLY:
            self._n2k_writer = self.define_n2k_writer()
        else:
            self._n2k_writer = None
        self._app_protocol = mode.lower()
        self._stopflag = False
        self._timer = None
        self._state = self.NOT_READY
        self._trace_msg = opts.get('trace_messages', bool, False)
        self._trace_raw = opts.get('trace_raw', bool, False)
        self._trace_msg = self._trace_msg or self._trace_raw
        if self._trace_msg:
            self.open_trace_file()
        self._check_in_progress = False
        self._separator = None
        self._separator_len = 0
        self._has_run = False
        self._status = None
        self._count_stamp = 0
        self._rate = 0.0
        self._rate_s = 0.0

    def start_timer(self):
        self._timer = threading.Timer(self._report_timer, self.timer_lapse)
        self._timer.name = self._name + "timer"
        _logger.debug("%s start lapse time %4.2f" % (self._timer.name, self._report_timer))
        self._timer.start()

    def timer_lapse(self):
        _logger.debug("Timer lapse => total number of messages:%g" % self._total_msg)
        if self._total_msg-self._last_msg_count == 0 and self._direction != self.WRITE_ONLY:
            # no message received
            _logger.warning("Coupler %s:No NMEA messages received in the last %4.1f sec" %
                            (self._name, self._timeout))
            self.check_connection()

        t = time.monotonic()
        self._rate = (self._total_msg - self._last_msg_count) / (t - self._count_stamp)
        self._rate_s = (self._total_msg_s - self._last_msg_count_s) / (t - self._count_stamp)
        self._last_msg_count = self._total_msg
        self._last_msg_count_s = self._total_msg_s
        self._count_stamp = t
        _logger.info("Coupler %s NMEA message received:%d rate:%6.2f sent:%d rate:%6.2f" %
                     (self.name(), self._total_msg, self._rate, self._total_msg_s, self._rate_s))
        if not self._stopflag:
            self.start_timer()

    def request_start(self):
        if self._autostart:
            _logger.info("Starting coupler %s" % self._name)
            super().start()

    def has_run(self):
        return self._has_run

    def force_start(self):
        self._autostart = True

    def define_n2k_writer(self):
        '''
        To be redefined in subclasses when the standard writer does not fit
        :return: an instance of a class implementing 'send_n2k_msg'
        '''
        writer = NMEA2000Writer(self, 50)
        writer.start()
        return writer

    def stop_writer(self):
        if self._n2k_writer is not None:
            self._n2k_writer.stop()

    def run(self):
        self._has_run = True
        self._startTS = time.time()
        self.start_timer()
        self._count_stamp = time.monotonic()
        nb_attempts = 0
        while not self._stopflag:
            if self._state == self.NOT_READY:
                if not self.open():
                    nb_attempts += 1
                    if nb_attempts > self._max_attempt:
                        _logger.error("Failed to open %s after %d attempts => coupler stops" % (
                            self.name(), self._max_attempt
                        ))
                        break
                    time.sleep(self._open_delay)
                    continue
                else:
                    nb_attempts = 0

            if self._direction == self.WRITE_ONLY:
                if self._stopflag:
                    break
                time.sleep(1.0)
                continue

            try:
                msg = self.read()
                if msg.type == NULL_MSG:
                    _logger.warning("No data from %s => close connection" % self._name)
                    self.close()
                    continue
                else:
                    _logger.debug(msg.printable())

            except CouplerTimeOut:
                continue
            except (socket.timeout, CouplerReadError):
                if self._stopflag:
                    break
                else:
                    continue
            except Exception as e:
                # catch all
                _logger.error("Un-caught exception during coupler %s read: %s" % (self._name, e))
                self.close()
                continue
            # good data received - publish
            self._total_msg += 1
            self._state = self.ACTIVE
            self.publish(msg)
        self.stop()
        self.close()
        _logger.info("%s coupler thread stops"%self._name)

    def register(self, pub):
        self._publishers.append(pub)
        # print("Coupler %s register %s" % (self._name, pub.name()))

    def deregister(self, pub):
        try:
            self._publishers.remove(pub)
        except ValueError:
            _logger.warning("Removing non attached publisher %s" % pub.descr())
            pass

    def publish(self, msg):
        # print("Publishing on %d publishers" % len(self._publishers))
        fault = False
        for p in self._publishers:
            try:
                p.publish(msg)
            except PublisherOverflow:
                _logger.error("Publisher %s in overflow, removing..." % p.name())
                if not fault:
                    faulty_pub = []
                    fault = True
                faulty_pub.append(p)

        if fault:
            for p in faulty_pub:
                self._publishers.remove(p)
            if len(self._publishers) == 0:
                _logger.error("Coupler %s as no publisher" % self._name)

    def send_msg_gen(self, msg: NavGenericMsg):
        if not self._configmode:
            if self._direction == self.READ_ONLY:
                _logger.error("Coupler %s attempt to write on a READ ONLY coupler" % self.name())
                return False
            self._total_msg_s += 1
            if msg.type == N2K_MSG:
                if self._n2k_writer is None:
                    _logger.error("%s cannot send NMEA2000 messages - protocol mismatch" % self._name)
                    return False
                self.trace_n2k_raw(msg.msg.pgn, msg.msg.da, msg.msg.prio, msg.msg.payload, direction=self.TRACE_OUT)
                self._n2k_writer.send_n2k_msg(msg.msg)
                return True
            else:
                return self.send(msg)
        else:
            return True

    def total_input_msg(self):
        return self._total_msg

    def total_output_msg(self):
        return self._total_msg_s

    def name(self):
        return self._name

    def state(self):
        return self._state

    def protocol(self):
        return self._app_protocol

    def input_rate(self):
        return self._rate

    def output_rate(self):
        return self._rate_s

    def stop(self):
        _logger.info("Stopping %s coupler" % self._name)
        self._stopflag = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self.stop_writer()

    def open(self) -> bool:
        raise NotImplementedError("To be implemented in subclass")

    def close(self):
        raise NotImplementedError("To be implemented in subclass")

    def read(self) -> NavGenericMsg:
        raise NotImplementedError("To be implemented in subclass")

    def send(self, msg: NavGenericMsg):
        raise NotImplementedError("To be implemented in subclass")

    def check_connection(self):
        # raise NotImplementedError("To be implemented in subclass")
        pass

    def resolve_ref(self, name):
        reference = self._opts[name]
        return NavigationConfiguration.get_conf().get_object(reference)

    def open_trace_file(self):
        trace_dir = NavigationConfiguration.get_conf().get_option('trace_dir', '/var/log')
        date_stamp = datetime.datetime.now().strftime("%y%m%d-%H%M")
        filename = "TRACE-%s-%s.log" % (self.name(), date_stamp)
        filepath = os.path.join(trace_dir, filename)
        _logger.info("Opening trace file %s" % filepath)
        try:
            self._trace_fd = open(filepath, "w")
        except IOError as e:
            _logger.error("Trace file error %s" % e)
            self._trace_msg = False
            self._trace_raw = False

    def trace(self, direction, msg: NavGenericMsg):
        if self._trace_msg:
            if direction == self.TRACE_IN:
                fc = "%d>" % self._total_msg
            else:
                fc = "%d<" % self._total_msg_s
            self._trace_fd.write(fc)
            out_msg = msg.printable()
            self._trace_fd.write(out_msg)
            self._trace_fd.write('\n')

    def trace_raw(self, direction, msg):
        if self._trace_raw:
            if direction == self.TRACE_IN:
                fc = "R%d#>" % self._total_msg
            else:
                fc = "R%d#<" % self._total_msg_s
            # l = len(msg) - self._separator_len
            # not all messages have the CRLF included to be further checked
            self._trace_fd.write(fc)
            self._trace_fd.write(msg.decode())
            self._trace_fd.write('\n')

    def trace_n2k_raw(self, pgn, sa, prio, data, direction=TRACE_IN):
        if self._trace_msg and self._trace_raw:
            if direction == self.TRACE_IN:
                fc = "N%d#>" % self._total_msg
            else:
                fc = "N#%d<" % self._total_msg_s
            self._trace_fd.write("%s%06d|%05X|%3d|%d|%s\n" % (fc, pgn, pgn, sa, prio, data.hex()))

    def add_event_trace(self, message: str):
        if self._trace_msg:
            self._trace_fd.write("Event#>")
            self._trace_fd.write(message)
            self._trace_fd.write('\n')

    def encode_nmea2000(self, msg: NMEA2000Msg) -> NavGenericMsg:
        raise NotImplementedError("To be implemented in subclass")

    def validate_n2k_frame(self, frame):
        raise NotImplementedError("To be implemented in subclass")

