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
from can import Bus, Message, CanOperationError, CanTimeoutError
from nmea2000.nmea2000_msg import NMEA2000Msg, FastPacketHandler, FastPacketException
from nmea2000.nmea2k_pgndefs import PGNDef, PGNDefinitions, N2KUnknownPGN
from utilities.message_trace import NMEAMsgTrace, MessageTraceError
import threading
import queue

_logger = logging.getLogger("ShipDataServer." + __name__)


class SocketCanError(Exception):
    pass


class SocketCANInterface(threading.Thread):

    def __init__(self, channel, out_queue, trace=False):

        super().__init__(name="CAN-if-%s" % channel)
        self._channel = channel
        try:
            self._bus = Bus(channel=channel, interface="socketcan", bitrate=250000)
        except CanOperationError as e:
            _logger.error("Error initializing CAN Channel %s: %s" % (channel, e))
            raise SocketCanError
        self._iso_queue = out_queue
        self._stop_flag = False
        self._data_queue = None
        self._in_queue = queue.Queue(20)
        self._fp_handler = FastPacketHandler(self)
        if trace:
            try:
                self._trace = NMEAMsgTrace(self.name)
            except MessageTraceError:
                self._trace = None
        else:
            self._trace = None

    def stop(self):
        self._stop_flag = True

    def set_data_queue(self, data_queue: queue.Queue):
        self._data_queue = data_queue

    def run(self):

        while not self._stop_flag:

            try:
                msg = self._bus.recv(1.0)
            except CanOperationError as e:
                _logger.error("Error receiving message from channel %s: %s" % (self._channel, e))
                continue
            except CanTimeoutError:
                _logger.debug("CAN timeout")
                continue
            if msg is None:
                continue

            if not msg.is_extended_id or msg.is_remote_frame:
                continue
            if self._trace is not None:
                self._trace.trace_raw(NMEAMsgTrace.TRACE_IN, str(msg))
            can_id = msg.arbitration_id
            sa = can_id & 0xFF
            pgn, da = PGNDef.pgn_pdu1_adjust((can_id >> 8) & 0x1FFFF)
            prio = (can_id >> 26) & 0x7
            data = msg.data
            # Fast packet handling
            if self._fp_handler.is_pgn_active(pgn, sa, data):
                try:
                    data = self._fp_handler.process_frame(pgn, sa, data)
                except FastPacketException as e:
                    _logger.error("YDCoupler Fast packet error %s pgn %d sa %d data %s" % (e, pgn, sa, data.hex()))
                    continue
                if data is None:
                    continue
            else:
                try:
                    fp = PGNDefinitions.pgn_definition(pgn).fast_packet()
                except N2KUnknownPGN:
                    fp = False
                if fp:
                    self._fp_handler.process_frame(pgn, sa, data)
                    continue
            # end fast packet handling

            n2k_msg = NMEA2000Msg(pgn, prio, sa, da, data)

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

            #  write section

            # messaging pacing to be implemented
            try:
                msg = self._in_queue.get_nowait()
            except queue.Empty:
                continue
            if self._trace is not None:
                self._trace.trace_raw(NMEAMsgTrace.TRACE_OUT, str(msg))
            try:
                self._bus.send(msg, 5.0)
            except CanOperationError as e:
                _logger.error("Error receiving message from channel %s: %s" % (self._channel, e))
                continue
            except CanTimeoutError:
                _logger.debug("CAN timeout")
                continue
            #end of the run loop

        if self._trace is not None:
            self._trace.stop_trace()
        self._bus.shutdown()

    def send(self, n2k_msg: NMEA2000Msg):

        # Fast Packet to be handled
        # Currently FastPacket messages are discarded
        if PGNDefinitions.pgn_definition(n2k_msg.pgn).fast_packet():
            _logger.error("Fast packet messages not implemented")
            return

        can_id = n2k_msg.sa
        pf = (n2k_msg.pgn >> 8) & 0xFF
        if pf < 240:
            can_id |= (n2k_msg.pgn + n2k_msg.da) << 8
        else:
            can_id |= n2k_msg.pgn
        can_id |= n2k_msg.prio << 26

        msg = Message(arbitration_id=can_id, is_extended_id=True, data=n2k_msg.payload)

        try:
            self._in_queue.put(msg, timeout=5.0)
        except queue.Full:
            _logger.error("Socket CAN Write buffer full")







