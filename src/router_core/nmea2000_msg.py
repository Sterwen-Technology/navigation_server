# -------------------------------------------------------------------------------
# Name:        nmea2000_msg
# Purpose:     Manages all NMEA2000 messages internal representation
#
# Author:      Laurent Carré
#
# Created:     26/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------
import binascii
import queue
import threading
import time
import logging
from google.protobuf.json_format import MessageToJson
import base64
import struct

# from nmea2000.nmea2k_pgndefs import *
# from nmea2000.nmea2k_encode_decode import BitField

from generated.nmea2000_pb2 import nmea2000pb
from router_common import NavGenericMsg, N2K_MSG, N2KDecodeException, NULL_MSG, N2KUnknownPGN
from .nmea0183_msg import NMEAInvalidFrame
from .nmea0183_msg import process_nmea0183_frame, NMEA0183Msg
from router_common import format_timestamp, find_pgn


_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KRawDecodeError(Exception):
    pass


class N2KEncodeError(Exception):
    pass


class NMEA2000Msg:

    __slots__ = ('_pgn', '_prio', '_sa', '_da', '_is_iso', '_ts', '_fast_packet', '_payload')

    ts_format = "%H:%M:%S.%f"
    struct_2b = struct.Struct("<H")
    pgn_service = (59392, 59904, 60928, 65240, 126208, 126464, 126993, 126996, 126998)

    def __init__(self, pgn: int, prio: int = 0, sa: int = 0, da: int = 0, payload: bytearray = None, timestamp=0.0,
                 protobuf=None):
        self._pgn = pgn
        if protobuf is None:
            self._prio = prio
            self._sa = sa
            self._da = da
            # change in version 1.3 => become float and referenced to the epoch
            # change in version 1.5 => timestamp is kept from original one
            if timestamp == 0.0:
                self._ts = time.time()
            else:
                self._ts = timestamp
            #  Corrected on Jan 12 2024 fast packet can have a payload < 8 Fast packet PGN must be transmitted in
            #   Fast packet mode whatever is the length

            self._payload = payload
            self._check_fast_packet()
        else:
            self.from_protobuf(protobuf)
        # define if the PGN is part of ISO and base protocol (do not carry navigation data)
        self._check_protocol()

    def _check_fast_packet(self):
        if self._pgn < 0x10000:
            self._fast_packet = False
        elif 0x10000 >= self._pgn < 0x1F000:
            self._fast_packet = True
        elif self._pgn >= 0x1FF00:
            self._fast_packet = True
        elif len(self._payload) > 8:
            self._fast_packet = True
        else:
            self._fast_packet = False

    def _check_protocol(self):
        if self._pgn in self.pgn_service:
            self._is_iso = True
        else:
            self._is_iso = False

    @property
    def pgn(self) -> int:
        return self._pgn

    @property
    def prio(self) -> int:
        return self._prio

    @property
    def sa(self) -> int:
        return self._sa

    @sa.setter
    def sa(self, address):
        self._sa = address

    @property
    def da(self) -> int:
        return self._da

    @property
    def payload(self) -> bytearray:
        return self._payload

    @property
    def fast_packet(self) -> bool:
        return self._fast_packet

    @property
    def is_iso_protocol(self) -> bool:
        return self._is_iso

    # The following 2 methods are for compatibility with NavGenericMsg
    @property
    def type(self):
        return N2K_MSG

    @property
    def msg(self):
        return self

    @property
    def timestamp(self) -> float:
        return self._ts

    def display(self):
        pgn_def = find_pgn(self._pgn)
        print("PGN %d|%04X|%s|time:%s" % (self._pgn, self._pgn, pgn_def.name,
                                          format_timestamp(self._ts, self.ts_format)))

    def __str__(self):
        if self._pgn == 0:
            return "Dummy PGN 0"
        else:
            return self.format2()

    def format1(self):
        '''
        Generate a string to display the message with PGN name
        '''
        try:
            pgn_def = find_pgn(self._pgn)
            name = pgn_def.name
        except N2KUnknownPGN:
            name = "Unknown PGN"
        if self._payload is None:
            payload = " "
        else:
            payload = self._payload.hex()
        return "PGN %d|%04X|%s sa=%d da=%d time=%s fp=%s data:%s" % (self._pgn, self._pgn, name, self._sa, self._da,
                                                                     format_timestamp(self._ts, self.ts_format),
                                                                     self._fast_packet, self._payload.hex())

    def format2(self):
        '''
        Generate a string to display the message with PGN number
        '''
        if self._payload is None:
            payload = " "
        else:
            payload = self._payload.hex()
        return "2K|%d|%04X|%d|%d|%d|%s|%s" % (self._pgn, self._pgn, self._prio, self._sa, self._da,
                                              format_timestamp(self._ts, self.ts_format), payload)

    def header_str(self):
        return f"PGN{self._pgn}|SA{self.sa}|DA{self.da}"

    def as_protobuf(self, res: nmea2000pb):

        res.pgn = self._pgn
        res.priority = self._prio
        res.sa = self._sa
        res.da = self._da
        try:
            val = self._ts
            res.timestamp = val
        except ValueError:
            _logger.error("Invalid time stamp %s %d on PGN %d" % (type(val), val, self._pgn))
        try:
            res.payload = bytes(self._payload)
        except TypeError as e:
            _logger.error("Type error %s on payload PGN %d type %s" % (e, self._pgn, type(self._payload)))
        return res

    def from_protobuf(self, pb_msg: nmea2000pb):
        self._sa = pb_msg.sa
        self._da = pb_msg.da
        self._prio = pb_msg.priority
        self._ts = pb_msg.timestamp
        self._payload = pb_msg.payload

    def serialize(self):
        return MessageToJson(self.as_protobuf())

    def decode(self):
        try:
            pgn_def = find_pgn(self._pgn)
        except N2KUnknownPGN:
            _logger.error("No definition for PGN %d => cannot decode" % self._pgn)
            return
        if self._payload is None:
            _logger.error("NMEA2000 Decode with no payload: %s" % self.format1())
            raise N2KDecodeException
        try:
            return pgn_def.decode_pgn_data(self._payload)
        except N2KDecodeException as e:
            _logger.error("%s ignoring" % str(e))
            return None

    def asPDGY(self):
        try:
            msg_data = b'!PDGY,%d,%1d,%d,%d,%d,%s\r\n' % (self._pgn, self._prio, self._sa, self._da, self._ts,
                                                      base64.b64encode(self._payload))
        except TypeError:
            _logger.error("NMEA2000 Encoding (asPDGY) error on payload on PGN %d" % self._pgn)
            raise N2KEncodeError
        return msg_data

    def asPGNST(self):
        msg_data = b'!PGNST,%d,%1d,%d,%d,%s\r\n' % (self._pgn, self._prio, self._sa, self._ts, self._payload.hex())
        return msg_data

    def get_manufacturer(self) -> int:
        '''
        Read the manufacturer code in the payload. It is assumed that the message includes the Mfg Code
        No checj here on message type
        :return:
        manufacturer code on int (11bits)
        '''
        mfg = self.struct_2b.unpack(self._payload[:2])[0] & (2**11 - 1)
        # print("PGN", self._pgn, "SA", self._sa, ":", self._payload.hex(), "mfg=", mfg, "%4X" % mfg)
        return mfg


def fromProprietaryNmea(msg: NMEA0183Msg) -> NMEA2000Msg:
    if msg.address() == b'PDGY':
        return decodePGDY(msg)
    else:
        raise ValueError


def decodePGDY(msg: NMEA0183Msg) -> NMEA2000Msg:
    fields = msg.fields()
    if len(fields) == 6:
        ''' Receive message'''
        da = int(fields[3])
        if da == 0:
            da = 255
        rmsg = NMEA2000Msg(
            pgn=int(fields[0]),
            prio=int(fields[1]),
            sa=int(fields[2]),
            da=da,
            payload=base64.b64decode(fields[5])
        )
    elif len(fields) == 3:
        ''' Transmit message'''
        da = int(fields[1])
        if da == 0:
            da = 255
        try:
            bin_data = base64.b64decode(fields[2])
        except binascii.Error as err:
            _logger.error(f"Cannot convert binascii {fields[2]}: {err}")
            raise N2KRawDecodeError(f"PGDY decode error of base64 string {fields[2]}")

        rmsg = NMEA2000Msg(
            pgn=int(fields[0]),
            da=da,
            payload=bin_data
        )
    else:
        raise N2KRawDecodeError("PDGY message format error => number of fields:%d" % len(fields))
    return rmsg


def fromPGDY(frame) -> NMEA2000Msg:
    '''
    Directly transform a PDGY NMEA0183 proprietary frame into a N2K internal message
    If this is not a PDGY message, then return that message without processing
    :param frame: bytearray with the NMEA0183 frame
    :return a NavGenericMsg:
    '''
    msg = process_nmea0183_frame(frame, checksum=False)
    if msg.type == NULL_MSG:
        return msg
    if msg.address() != b'PDGY' or msg.delimiter() != ord('!'):
        # print("Delimiter:", msg.delimiter(), "address:", msg.address())
        _logger.warning("PDGY sentence invalid: %s" % str(msg))
        raise NMEAInvalidFrame

    try:
        rmsg = decodePGDY(msg)
    except N2KRawDecodeError as e:
        _logger.error("PDGY sentence error: %s %s" % (e, str(msg)))
        raise
    _logger.debug("NMEA2000 message from PGDY:%s" % rmsg.format1())
    return rmsg


def fromPGNST(frame):
    raise NotImplementedError("PGNST decoding")



class NMEA2000Writer(threading.Thread):
    '''
    This class implements the buffered write on CAN interface
    It handles the conversion towards the actual interface protocol
    Queuing of messages and throughput management

    '''

    def __init__(self, instrument, max_throughput):
        self._name = instrument.object_name() + '-Writer'
        _logger.info('Creating writer:%s' % self._name)
        super().__init__(name=self._name, daemon=True)
        self._instrument = instrument
        self._max_throughput = max_throughput
        self._queue = queue.Queue(30)
        self._stop_flag = False
        self._interval = 1.0 / max_throughput
        self._last_msg_ts = time.monotonic()

    def send_n2k_msg(self, msg: NMEA2000Msg):
        for msg in self._instrument.encode_nmea2000(msg):
            self._queue.put(msg)

    def run(self):
        while not self._stop_flag:
            msg = self._queue.get()
            if msg.type == NULL_MSG:
                break
            actual = time.monotonic()
            delta = actual - self._last_msg_ts
            if delta < self._interval:
                time.sleep(self._interval - delta)
                actual = time.monotonic()
            self._last_msg_ts = actual
            _logger.debug("N2K Writer %s sending:%s" % (self._name, msg.raw))
            self._instrument.send(msg)
            self._instrument.validate_n2k_frame(msg.raw)
        _logger.info("%s thread stops" % self._name)

    def stop(self):
        self._stop_flag = True
        self._queue.put(NavGenericMsg(NULL_MSG))
