# -------------------------------------------------------------------------------
# Name:        nmea2k_iso_transport
# Purpose:     Handle ISO J1939/21 Transport protocol
#
# Author:      Laurent Carré
#
# Created:     03/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

#  implementation notes
#   Partial implementation with only Broadcast mode - limited defense

import logging
import struct
import time
import threading


from router_core.nmea2000_msg import NMEA2000Msg
from nmea2000.nmea2k_pgn_definition import PGNDef

_logger = logging.getLogger("ShipDataServer." + __name__)

(TP_CREATED, TP_ANNOUNCED, TP_IN_TRANSMISSION, TP_END) = range(1, 5)


class IsoTransportException(Exception):
    pass


class IsoTransportTransaction:

    __slots__ = ("_pgn", "_total_size", "_nb_packets", "_state", "_transmitted_packets", "_buffer", "_start_time",
                 "_sa", "_prio", '_timer')
    _bam_struct = struct.Struct("<BHBBHB")

    def __init__(self):
        self._pgn = 0
        self._state = TP_CREATED
        self._nb_packets = 0
        self._transmitted_packets = 0

    def incoming_bam_transaction(self, sa: int, prio: int, frame: bytearray):
        _logger.debug("ISO Transport => new transaction for address %d" % sa)
        if frame[0] != 32:
            raise IsoTransportException("ISO Transport Non BAM transaction: %d" % frame[0])
        self._sa = sa
        self._prio = prio
        dec_val = self._bam_struct.unpack(frame)
        self._total_size = dec_val[1]
        self._nb_packets = dec_val[2]
        self._pgn, da = PGNDef.pgn_pdu1_adjust(dec_val[4] | (dec_val[5] << 16))
        self._state = TP_IN_TRANSMISSION
        self._buffer = bytearray(self._total_size)
        self._start_time = time.monotonic()
        self._timer = threading.Timer(0.1 * self._nb_packets, self.timer_lapse)
        _logger.debug("ISO Transport => Transaction for PGN %d l=%d" % (self._pgn, self._total_size))
        return self

    def incoming_packet(self, frame: bytearray):
        if self._state != TP_IN_TRANSMISSION:
            raise IsoTransportException
        seq_num = frame[0]
        _logger.debug("ISO transport incoming packet from sa %d seq %d" % (self._sa, seq_num))
        ptr = (seq_num - 1) * 7
        if ptr + 7 > self._total_size:
            # partial fill of last buffer
            length = self._total_size - ptr
        else:
            length = 7
        self._buffer[ptr: ptr + length] = frame[1: length + 1]
        self._transmitted_packets += 1
        if self._transmitted_packets == self._nb_packets:
            # transmission is over
            self._state = TP_END
            self._timer.cancel()
            # now building the NMEA Message
            msg = NMEA2000Msg(self._pgn, prio=self._prio, sa=self._sa, da=255, payload=self._buffer,
                               timestamp=self._start_time)
            _logger.debug("ISO Transport message=%s" % msg.format1())
            return msg
        else:
            return None

    def timer_lapse(self):
        _logger.error("ISO Transport transaction timeout sa=%d PGN=%d" % (self._sa, self._pgn))
        self._state = TP_END

    def outgoing_bam_transaction(self, msg: NMEA2000Msg) -> NMEA2000Msg:
        payload = bytearray(8)
        self._total_size = len(msg.payload)
        self._buffer = msg.payload
        self._nb_packets = self._total_size // 7
        if self._total_size % 7 != 0:
            self._nb_packets += 1
        pgn_low = msg.pgn & 0xFFFF
        pgn_up = (msg.pgn >> 16) & 0xFF
        self._bam_struct.pack_into(payload, 0, 32, self._total_size, self._nb_packets, 0xFF, pgn_low, pgn_up)
        return NMEA2000Msg(60416, 7, msg.sa, 255, payload)

    def split_message(self):
        data = bytearray(8)
        seq_num = 1
        ptr = 0
        while seq_num <= self._nb_packets:
            data[0] = seq_num
            if seq_num == self._nb_packets:
                l = self._total_size - ptr
                data[1: l+1] = self._buffer[ptr:]
                r = 7 - l
                if r != 0:
                    # pad
                    for p in (l, 7):
                        data[p] = 0xFF
            else:
                data[1:] = self._buffer[ptr: ptr + 7]
                ptr += 7
            seq_num += 1
            yield data
        return


class IsoTransportHandler:

    def __init__(self):
        self._transactions = {}

    def new_transaction(self, sa, prio, frame):
        try:
            transact = IsoTransportTransaction().incoming_bam_transaction(sa, prio, frame)
        except IsoTransportException as e:
            _logger.error("ISO Transport error: %s" % str(e))
            return
        self._transactions[sa] = transact

    def new_output_transaction(self, msg: NMEA2000Msg):
        transact = IsoTransportTransaction()
        tpcm_msg = transact.outgoing_bam_transaction(msg)
        return transact, tpcm_msg

    def incoming_packet(self, sa, frame):
        try:
            transact = self._transactions[sa]
        except KeyError:
            _logger.error("Unknown transport transaction from sa:%d" % sa)
            raise IsoTransportException
        try:
            result = transact.incoming_packet(frame)
        except IsoTransportException as err:
            # the whole transaction is aborted
            _logger.error("ISO Transport aborted transaction (likely timeout)")
            del self._transactions[sa]
            raise

        if result is not None:
            # transaction is over
            del self._transactions[sa]
        return result











