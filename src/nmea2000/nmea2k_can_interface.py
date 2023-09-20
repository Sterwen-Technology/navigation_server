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

import logging
from can import Bus, Message, CanOperationError, CanTimeoutError, Notifier, Listener
from nmea2000.nmea2000_msg import NMEA2000Msg, FastPacketHandler, FastPacketException
from nmea2000.nmea2k_pgndefs import PGNDef, PGNDefinitions, N2KUnknownPGN
from utilities.message_trace import NMEAMsgTrace, MessageTraceError
import threading
import queue
import time

_logger = logging.getLogger("ShipDataServer." + __name__)


class SocketCanError(Exception):
    pass


class SocketCANInterface(threading.Thread):

    (BUS_NOT_CONNECTED, BUS_CONNECTED, BUS_READY, BUS_SENS_ALLOWED) = range(0, 4)

    def __init__(self, channel, out_queue, trace=False):

        super().__init__(name="CAN-if-%s" % channel)
        self._channel = channel
        self._bus = None
        self._iso_queue = out_queue
        self._stop_flag = False
        self._data_queue = None
        self._allowed_send = threading.Event()
        self._allowed_send.clear()
        self._bus_ready = threading.Event()
        self._bus_ready.clear()
        self._in_queue = queue.Queue(30)
        self._bus_queue = queue.Queue(50)
        self._fp_handler = FastPacketHandler(self)
        self._notifier = None
        self._listener = NMEA2000MsgListener(self, self._bus_queue)
        self._state = self.BUS_NOT_CONNECTED

        if trace:
            try:
                self._trace = NMEAMsgTrace(self.name)
            except MessageTraceError:
                self._trace = None
        else:
            self._trace = None

    def start(self):
        # connect to the CAN bus
        try:
            self._bus = Bus(channel=self._channel, interface="socketcan", bitrate=250000)
        except CanOperationError as e:
            _logger.error("Error initializing CAN Channel %s: %s" % (self._channel, e))
            raise SocketCanError
        self._notifier = Notifier(self._bus, [self._listener])
        self._state = self.BUS_CONNECTED
        super().start()

    def stop(self):
        self._stop_flag = True
        if self._notifier is not None:
            self._notifier.stop()

    def set_data_queue(self, data_queue: queue.Queue):
        self._data_queue = data_queue

    def wait_for_bus_ready(self):
        self._bus_ready.wait()
        _logger.debug("NMEA CAN Interface BUS ready")

    def allow_send(self):
        self._allowed_send.set()

    def read_bus(self, msg_recv: Message):
        # sub-function to read the bus and perform Fast packet reassembly
        # return a NMEA200Msg when a valid message as been received or reassembled

        if self._trace is not None:
            self._trace.trace_raw(NMEAMsgTrace.TRACE_IN, str(msg_recv))
        can_id = msg_recv.arbitration_id
        sa = can_id & 0xFF
        pgn, da = PGNDef.pgn_pdu1_adjust((can_id >> 8) & 0x1FFFF)
        prio = (can_id >> 26) & 0x7
        data = msg_recv.data
        # Fast packet handling
        if self._fp_handler.is_pgn_active(pgn, sa, data):
            try:
                data = self._fp_handler.process_frame(pgn, sa, data)
            except FastPacketException as e:
                _logger.error("CAN interface Fast packet error %s pgn %d sa %d data %s" % (e, pgn, sa, data.hex()))
                return None
            if data is None:
                return None
        else:
            try:
                fp = PGNDefinitions.pgn_definition(pgn).fast_packet()
            except N2KUnknownPGN:
                fp = False
            if fp:
                self._fp_handler.process_frame(pgn, sa, data)
                return None
        # end fast packet handling
        n2k_msg = NMEA2000Msg(pgn, prio, sa, da, data)
        if n2k_msg is not None:
            if n2k_msg.is_iso_protocol:
                try:
                    self._iso_queue.put(n2k_msg, block=False)
                except queue.Full:
                    _logger.warning("ISO layer queue full, message ignored")
            elif self._data_queue is not None:
                try:
                    self._data_queue.put(n2k_msg, block=False)
                except queue.Full:
                    _logger.warning("CAN Data queue full, message lost")
        # once the first message is received, the bus is considered as ready
        if self._state != self.BUS_READY:
            self._bus_ready.set()
            self._state = self.BUS_READY
        # _logger.debug("NMEA2000 message received %s" % n2k_msg.format1())

    def run(self):

        #  Run loop
        last_write_time = time.monotonic()
        while not self._stop_flag:


            # messaging pacing to be implemented
            if time.monotonic() - last_write_time < 0.05:
                continue

            try:
                msg = self._in_queue.get_nowait()
            except queue.Empty:
                continue
            if self._trace is not None:
                self._trace.trace_raw(NMEAMsgTrace.TRACE_OUT, str(msg))
            try:
                _logger.debug("CAN sending: %s" % str(msg))
                self._bus.send(msg, 5.0)
                last_write_time = time.monotonic()
            except CanOperationError as e:
                _logger.error("Error receiving message from channel %s: %s" % (self._channel, e))
                continue
            except CanTimeoutError:
                _logger.error("CAN send timeout error - message lost")
                continue
            # end of the run loop

        # thread exit section
        if self._trace is not None:
            self._trace.stop_trace()
        self._bus.shutdown()

    def send(self, n2k_msg: NMEA2000Msg):

        if not self._allowed_send.is_set() and n2k_msg.pgn not in [59904, 60928]:
            _logger.error("Trying to send messages on the BUS while no address claimed")
            return

        can_id = n2k_msg.sa
        pf = (n2k_msg.pgn >> 8) & 0xFF
        if pf < 240:
            can_id |= (n2k_msg.pgn + n2k_msg.da) << 8
        else:
            can_id |= n2k_msg.pgn << 8
        can_id |= n2k_msg.prio << 26

        _logger.debug("CAN interface send in queue message: %s" % n2k_msg.format1())

        # Fast packet processing
        if PGNDefinitions.pgn_definition(n2k_msg.pgn).fast_packet():
            for data in self._fp_handler.split_message(n2k_msg.pgn, n2k_msg.payload):
                msg = Message(arbitration_id=can_id, is_extended_id=True, timestamp=time.monotonic(), data=data)
                try:
                    self._in_queue.put(msg, timeout=5.0)
                except queue.Full:
                    _logger.error("Socket CAN Write buffer full")
                    return False
        else:
            msg = Message(arbitration_id=can_id, is_extended_id=True, timestamp=time.monotonic(), data=n2k_msg.payload)
            try:
                self._in_queue.put(msg, timeout=5.0)
            except queue.Full:
                _logger.error("Socket CAN Write buffer full")
                return False
        return True


class NMEA2000MsgListener(Listener):

    def __init__(self, interface: SocketCANInterface, bus_queue: queue.Queue):
        # super().___init__()
        self._interface = interface
        self._bus_queue = bus_queue

    def on_message_received(self, msg: Message) -> None:
        if not msg.is_extended_id or msg.is_remote_frame:
            return
        # _logger.debug("CAN interface received: %s" % msg)
        self._interface.read_bus(msg)

    def on_error(self, exc: Exception) -> None:
        _logger.error("BUS CAN error: %s" % exc)









