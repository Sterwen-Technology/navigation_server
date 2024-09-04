#-------------------------------------------------------------------------------
# Name:        Coupler
# Purpose:     Abstract super class for all instruments
#
# Author:      Laurent Carré
#
# Created:     29/11/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import socket


import threading
import logging
import time
# from publisher import Publisher

from .publisher import PublisherOverflow
from router_common import NavGenericMsg, NULL_MSG, N2K_MSG, NavThread
from .nmea2000_msg import NMEA2000Msg, NMEA2000Writer
from router_common import NMEAMsgTrace, MessageTraceError
# from .nmea0183_to_nmea2k import NMEA0183ToNMEA2000Converter, Nmea0183InvalidMessage
from router_common import IncompleteMessage, resolve_ref, resolve_class
from .nmea0183_msg import NMEAInvalidFrame


_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class CouplerReadError(Exception):
    pass


class CouplerWriteError(Exception):
    pass


class CouplerTimeOut(CouplerReadError):
    pass


class CouplerNotPresent(Exception):
    pass


class CouplerOpenRefused(Exception):
    pass


class Coupler(NavThread):
    '''
    Base abstract class for all couplers
    '''

    (NOT_READY, OPEN, CONNECTED, ACTIVE) = range(4)
    (BIDIRECTIONAL, READ_ONLY, WRITE_ONLY) = range(10, 13)
    (NMEA0183, NMEA2000, NMEA_MIX, NON_NMEA) = range(20, 24)
    (TRACE_IN, TRACE_OUT) = range(30, 32)

    dir_dict = {'bidirectional': BIDIRECTIONAL,
                'read_only': READ_ONLY,
                'write_only': WRITE_ONLY}

    protocol_dict = {'nmea0183': NMEA0183, 'nmea2000': NMEA2000, 'nmea_mix': NMEA_MIX, 'non_nmea': NON_NMEA}

    def __init__(self, opts):
        object_name = opts['name']
        super().__init__(name=object_name)
        # self.name = object_name
        self._name = object_name
        self._opts = opts
        self._publishers = []
        self._configmode = False
        self._configpub = None
        self._startTS = 0
        self._total_msg = 0
        self._total_msg_raw = 0
        self._total_msg_s = 0
        self._last_msg_count = 0
        self._last_msg_count_s = 0
        self._last_msg_count_r = 0
        self._report_timer = opts.get('report_timer', float,  30.0)
        self._timeout = opts.get('timeout', float, 10.0)
        self._max_attempt = opts.get('max_attempt', int, 20)
        self._open_delay = opts.get('open_delay', float, 2.0)
        self._autostart = opts.get('autostart', bool, True)
        self._talker = opts.get('talker', str, None)
        if self._talker is not None:
            self._talker = self._talker.upper().encode()
        direction = opts.get('direction', str, 'bidirectional')
        # print(self.object_name(), ":", direction)
        self._direction = self.dir_dict.get(direction, self.BIDIRECTIONAL)
        self._mode_str = opts.get('protocol', str, 'nmea0183').lower()
        self._mode = self.protocol_dict[self._mode_str]
        _logger.info("Coupler %s mode %d direction %d" % (self._name, self._mode, self._direction))
        if self._mode == self.NMEA2000 and self._direction != self.READ_ONLY:
            self._n2k_writer = self.define_n2k_writer()
        else:
            self._n2k_writer = None
        self._stopflag = False
        self._suspend_flag = False
        self._timer = None
        self._state = self.NOT_READY
        self._trace_msg = opts.get('trace_messages', bool, False)
        self._trace_raw = opts.get('trace_raw', bool, False)
        # self._trace_msg = self._trace_msg or self._trace_raw
        if self._trace_msg or self._trace_raw:
            try:
                self._tracer = NMEAMsgTrace(object_name, self.__class__.__name__)
            except MessageTraceError:
                self._trace_msg = False
                self._trace_raw = False
        else:
            self._tracer = None
        self._check_in_progress = False
        self._fast_packet_handler = None
        self._separator = None
        self._separator_len = 0
        self._has_run = False
        self._count_stamp = 0
        self._rate = 0.0
        self._rate_s = 0.0
        self._rate_raw = 0.0
        #  NMEA0183 Conversion
        #
        self._nmea183_convert = opts.get('nmea0183_convert', bool, False)
        if self._nmea183_convert:
            try:
                converter_class = resolve_class('NMEA0183ToNMEA2000Converter')
                source = opts.get('source', int, 251)
                if source < 0 or source > 253:
                    _logger.error("%s incorrect SA for converted messages" % self.name)
                    source = 251
                self._converter = converter_class(source)
            except KeyError:
                _logger.error("NMEA0183 to NMEA2000 converter not found")
                self._converter = None
                self._nmea183_convert = False
        else:
            self._converter = None
        #
        #  message automatic processing
        #
        self._n2k_controller = None
        self._n2k_ctlr_name = opts.get('nmea2000_controller', str, None)
        # self._data_sink = None
        # self._data_sink_name = opts.get('data_sink', str, None)

    @property
    def fast_packet_handler(self):
        return self._fast_packet_handler

    @property
    def n2k_writer(self):
        return self._n2k_writer

    @property
    def n2k_controller(self):
        return self._n2k_controller

    @property
    def mode(self):
        return self._mode

    @property
    def publishers(self):
        return self._publishers

    def start_timer(self):
        self._timer = threading.Timer(self._report_timer, self.timer_lapse)
        self._timer.name = self._name + "-timer"
        _logger.debug("%s start lapse time %4.2f" % (self._timer.name, self._report_timer))
        self._timer.start()

    def timer_lapse(self):
        if self._state != self.NOT_READY:
            _logger.debug("Timer lapse => total number of messages:%g" % self._total_msg)
            if self._total_msg-self._last_msg_count == 0 and self._direction != self.WRITE_ONLY:
                # no message received
                _logger.warning("Coupler %s:No NMEA messages received in the last %4.1f sec" %
                                (self._name, self._timeout))
                self.check_connection()

            t = time.monotonic()
            self._rate = (self._total_msg - self._last_msg_count) / (t - self._count_stamp)
            self._rate_raw = (self.total_msg_raw() - self._last_msg_count_r) / (t - self._count_stamp)
            self._rate_s = (self._total_msg_s - self._last_msg_count_s) / (t - self._count_stamp)
            self._last_msg_count = self._total_msg
            self._last_msg_count_r = self.total_msg_raw()
            self._last_msg_count_s = self._total_msg_s
            self._count_stamp = t
            _logger.info("Coupler %s NMEA message received(process:%d rate:%6.2f; raw:%d rate:%6.2f sent:%d rate:%6.2f" %
                         (self.object_name(), self._total_msg, self._rate, self.total_msg_raw(), self._rate_raw,
                          self._total_msg_s, self._rate_s))
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

    def restart(self):
        '''
        To be redefined in subclasses that need to perform actions when the coupler is re-created and restarted
        Otherwise do nothing
        '''
        pass

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
            _logger.info("Stopping NMEA2000 Writer")
            self._n2k_writer.stop()

    def nrun(self):
        self._has_run = True
        # now resolve internal references
        if self._n2k_ctlr_name is not None:
            try:
                self._n2k_controller = resolve_ref(self._n2k_ctlr_name)
            except KeyError:
                pass
        # self._data_sink = self.resolve_ref(self._data_sink_name, "Data sink")

        self._startTS = time.time()
        self.start_timer()
        self._count_stamp = time.monotonic()
        nb_attempts = 0
        while not self._stopflag:
            #
            #   Open communication section
            #
            if self._state == self.NOT_READY:
                _logger.debug("Coupler %s start open sequence" % self.object_name())
                if nb_attempts >= self._max_attempt:
                    _logger.error("Failed to open %s after %d attempts => coupler stops" % (
                        self.object_name(), self._max_attempt
                    ))
                    break
                try:
                    if not self.open():
                        nb_attempts += 1
                        time.sleep(self._open_delay)
                        continue
                    else:
                        self._state = self.OPEN
                        _logger.debug("Coupler %s open OK" % self.object_name())
                        nb_attempts = 0
                except CouplerOpenRefused:
                    _logger.critical("Fatal exception on coupler %s" % self._name)
                    break

            #  write only section
            if self._direction == self.WRITE_ONLY or self._suspend_flag:
                if self._stopflag:
                    break
                time.sleep(1.0)
                continue

            #
            #  read section
            #  read sends a generator from version 1.8
            try:
                _logger.debug("Coupler %s start reading status %d" % (self.object_name(), self._state))
                for msg in self.read():
                    if msg.type == NULL_MSG:
                        _logger.warning("End of data from %s => close connection" % self._name)
                        self.close()
                        continue
                    else:
                        _logger.debug("%s push:%s" % (self.object_name(), msg))
                        # good data received - filter and publish
                        self._total_msg += 1
                        self._state = self.ACTIVE
                        self.publish(msg)
            except CouplerTimeOut:
                continue
            except (socket.timeout, CouplerReadError, IncompleteMessage):
                if self._stopflag:
                    break
                else:
                    continue
            except Exception as e:
                # catch all
                _logger.error("Un-caught exception during coupler %s read: %s" % (self._name, e))
                self.close()
                continue

            # end of run loop

        _logger.debug("%s coupler -> end of reading loop" % self._name)
        self.stop()
        self.close()
        self.stop_trace()
        _logger.info("%s coupler thread stops" % self._name)

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
                _logger.error("Publisher %s in overflow, removing..." % p.object_name())
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
        # first need to check if the coupler is ready to send a message 24-05-18
        if self._state < self.OPEN:
            # ok not ready
            if not self.is_alive() or self._stopflag:
                # the coupler is down or shutting down
                raise CouplerWriteError(f"Coupler {self.object_name()} is shutting down")
            _logger.error("Coupler %s not ready" % self.object_name())
            return False
        if not self._configmode:
            if self._direction == self.READ_ONLY:
                _logger.error("Coupler %s attempt to write on a READ ONLY coupler" % self.object_name())
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

    def total_msg_raw(self):
        return self._total_msg_raw

    def increment_msg_raw(self):
        self._total_msg_raw += 1

    def total_output_msg(self):
        return self._total_msg_s

    def object_name(self):
        return self._name

    def state(self):
        return self._state

    def protocol(self):
        return self._mode_str

    def input_rate(self):
        return self._rate

    def input_rate_raw(self):
        return self._rate_raw

    def output_rate(self):
        return self._rate_s

    def stop(self):
        if self._stopflag is True:
            _logger.debug("redundant call of stop for %s => no action" % self._name)
        else:
            _logger.info("Stopping %s coupler" % self._name)
            self.stop_communication()
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self.stop_writer()
            self._stopflag = True
            self._state = self.NOT_READY

    def stop_communication(self):
        # to be implemented in subclasses when specific action is to be taken
        pass

    def suspend(self):
        if self.is_alive():
            self._suspend()
            self._suspend_flag = True
            _logger.info("Coupler %s suspended" % self.object_name())

    def _suspend(self):
        # implement specific actions on suspend to be overloaded
        pass

    def resume(self):
        if self._suspend_flag:
            self._resume()
            self._suspend_flag = False
            _logger.info("Coupler %s resume" % self.object_name())

    def _resume(self):
        # implement specific actions on resume - to be overloaded
        pass

    def is_suspended(self) -> bool:
        return self._suspend_flag

    def read(self):
        fetch_next = True
        while fetch_next:
            msg = self._read()
            self.trace(NMEAMsgTrace.TRACE_IN, msg)
            _logger.debug("Read primary:%s", msg)
            if msg.type == N2K_MSG:
                if self._n2k_controller is not None and msg.msg.is_iso_protocol:
                    fetch_next = True
                    self._n2k_controller.send_message(msg.msg)
                else:
                    fetch_next = False
            else:
                fetch_next = False
                if self._nmea183_convert:
                    try:
                        for n2k_msg in self._converter.convert_to_n2kmsg(msg):
                            _logger.debug("Read valid N2K:%s", n2k_msg)
                            yield n2k_msg
                        return
                    except NMEAInvalidFrame:
                        if self._mode == self.NMEA2000:
                            fetch_next = True

        # _logger.debug("Read valid data:%s", msg)
        yield msg

    def _read(self) -> NavGenericMsg:
        '''
        This method only perform a basic read function without any filtering / processing
        :return: a NMEA message (either NMEA0183 or NMEA2000)
        '''
        raise NotImplementedError("Method _read To be implemented in subclass")

    def open(self) -> bool:
        raise NotImplementedError("To be implemented in subclass")

    def close(self):
        raise NotImplementedError("To be implemented in subclass")

    def send(self, msg: NavGenericMsg):
        raise NotImplementedError("To be implemented in subclass")

    def check_connection(self):
        # raise NotImplementedError("To be implemented in subclass")
        pass

    def trace(self, direction, msg: NavGenericMsg):
        if self._trace_msg and self._tracer is not None:
            self._tracer.trace(direction, msg)

    def stop_trace(self):
        if self._tracer is not None:
            # _logger.info("Coupler %s closing trace file" % self._name)
            self._tracer.stop_trace()
            self._tracer = None
            self._trace_raw = False
            self._trace_msg = False
        else:
            _logger.error("Coupler %s attempt closing inactive trace" % self._name)

    def start_trace_raw(self):
        if not self.is_alive():
            _logger.error("Coupler %s attempt to start traces while not running")
            return
        if self._tracer is not None:
            _logger.error("Coupler %s attempt to start traces while already active")
            return
        _logger.info("Starting traces on raw input on %s" % self.object_name())
        try:
            self._tracer = NMEAMsgTrace(self.object_name(), self.__class__.__name__)
            self._trace_raw = True
        except MessageTraceError:
            pass

    def trace_raw(self, direction, msg, strip_suffix: str = None):
        if self._trace_raw and self._tracer is not None:
            self._tracer.trace_raw(direction, msg, strip_suffix)

    def trace_n2k_raw(self, pgn, sa, prio, data, direction=TRACE_IN):
        if self._tracer is not None and self._trace_raw:
            self._tracer.trace_n2k_raw(pgn, sa, prio, data, direction)

    def add_event_trace(self, message: str):
        if self._tracer is not None:
            self._tracer.add_event_trace(message)

    def encode_nmea2000(self, msg: NMEA2000Msg) -> NavGenericMsg:
        raise NotImplementedError("To be implemented in subclass")

    def validate_n2k_frame(self, frame):
        raise NotImplementedError("To be implemented in subclass")

    def check_ctlr_msg(self, msg) -> bool:
        '''
        Check if the message is a service message for the NMEA2000 controller
        :param msg:
        :return: True if the message is directed to the NMEA2000 controller
        '''

        if self._n2k_controller is not None:
            n2kmsg = msg.msg
            if n2kmsg.is_iso_protocol():
                self._n2k_controller.send_message(n2kmsg)
                return True
        return False
