#-------------------------------------------------------------------------------
# Name:        Instrument
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
from publisher import Publisher
from configuration import NavigationConfiguration
from publisher import PublisherOverflow
from generic_msg import NavGenericMsg, NULL_MSG


_logger = logging.getLogger("ShipDataServer")


class InstrumentReadError(Exception):
    pass


class InstrumentTimeOut(InstrumentReadError):
    pass


class InstrumentNotPresent(Exception):
    pass


class Instrument(threading.Thread):
    '''
    Base abstract class for all instruments
    '''

    (NOT_READY, OPEN, CONNECTED, ACTIVE) = range(4)
    (BIDIRECTIONAL, READ_ONLY, WRITE_ONLY) = range(10, 13)
    (NMEA0183, NMEA2000) = range(20, 22)
    (TRACE_IN, TRACE_OUT) = range(30, 32)

    dir_dict = {'bidirectional': BIDIRECTIONAL,
                'read_only': READ_ONLY,
                'write_only': WRITE_ONLY}

    protocol_dict = {'nmea0183': NMEA0183, 'nmea2000': NMEA2000}

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
        self._talker = opts.get('talker', str, None)
        if self._talker is not None:
            self._talker = self._talker.upper().encode()
        self.get_mode(opts)
        direction = opts.get('direction', str, 'bidirectional')
        # print(self.name(), ":", direction)
        self._direction = self.dir_dict.get(direction, self.BIDIRECTIONAL)
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

    def get_mode(self, opts):
        mode = opts.get('protocol', str, 'nmea0183')
        self._mode = self.protocol_dict[mode.lower()]
        self._app_protocol = mode.lower()

    def start_timer(self):
        self._timer = threading.Timer(self._report_timer, self.timer_lapse)
        self._timer.name = self._name + "timer"
        _logger.debug("%s start lapse time %4.2f" % (self._timer.name, self._report_timer))
        self._timer.start()

    def timer_lapse(self):
        _logger.debug("Timer lapse => total number of messages:%g" % self._total_msg)
        if self._total_msg-self._last_msg_count == 0 and self._direction != self.WRITE_ONLY:
            # no message received
            _logger.warning("Instrument %s:No NMEA messages received in the last %4.1f sec" %
                            (self._name, self._timeout))
            self.check_connection()
        self._last_msg_count = self._total_msg
        self._last_msg_count_s = self._total_msg_s
        _logger.info("Instrument %s NMEA message received:%d sent:%d" % (self.name(), self._total_msg, self._total_msg_s))
        if not self._stopflag:
            self.start_timer()

    def run(self):
        self._startTS = time.time()
        self.start_timer()
        nb_attempts = 0
        while not self._stopflag:
            if self._state == self.NOT_READY:
                if not self.open():
                    nb_attempts += 1
                    if nb_attempts > self._max_attempt:
                        _logger.error("Failed to open %s after %d attempts => instrument stops" % (
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

            except InstrumentTimeOut:
                continue
            except (socket.timeout, InstrumentReadError):
                if self._stopflag:
                    break
                else:
                    continue
            except Exception as e:
                # catch all
                _logger.error("Un-caught exception during instrument %s read: %s" % (self._name, e))
                self.close()
                continue
            # good data received - publish
            self._total_msg += 1
            self._state = self.ACTIVE
            self.publish(msg)
        self.stop()
        self.close()
        _logger.info("%s instrument thread stops"%self._name)

    def register(self, pub):
        self._publishers.append(pub)
        # print("Instrument %s register %s" % (self._name, pub.name()))

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
                _logger.error("Instrument %s as no publisher" % self._name)

    def send_cmd(self, msg):
        if not self._configmode:
            if self._direction == self.READ_ONLY:
                _logger.error("Instrument %s attempt to write on a READ ONLY instrument" % self.name())
                return False
            self._total_msg_s += 1
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

    def stop(self):
        _logger.info("Stopping %s instrument"% self._name)
        self._stopflag = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def open(self):
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

    def default_sender(self):
        return False

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
                fc = "R# >"
            else:
                fc = "R# <"
            l = len(msg) - self._separator_len
            self._trace_fd.write(fc)
            self._trace_fd.write(msg[:l].decode())
            self._trace_fd.write('\n')

    def add_event_trace(self, message: str):
        if self._trace_msg:
            self._trace_fd.write("## Event:")
            self._trace_fd.write(message)
            self._trace_fd.write('\n')

