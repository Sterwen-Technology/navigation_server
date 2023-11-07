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
import queue
import threading
import time
from google.protobuf.json_format import MessageToJson
import base64

from nmea2000.nmea2k_pgndefs import *

from generated.nmea2000_pb2 import nmea2000pb
from nmea_routing.generic_msg import *
from nmea0183.nmea0183_msg import process_nmea0183_frame, NMEA0183Msg
from utilities.date_time_utilities import format_timestamp

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KRawDecodeError(Exception):
    pass


class N2KEncodeError(Exception):
    pass


class NMEA2000Msg:

    ts_format = "%H:%M:%S.%f"

    def __init__(self, pgn: int, prio: int = 0, sa: int = 0, da: int = 0, payload: bytes = None, timestamp=0.0):
        self._pgn = pgn
        self._prio = prio
        self._sa = sa
        self._da = da
        # define if the PGN is part of ISO and base protocol (do not carry navigation data)
        self._is_iso = PGNDef.pgn_for_controller(pgn)
        # change in version 1.3 => become float and referenced to the epoch
        # change in version 1.5 => timestamp is kept from original one
        if timestamp == 0.0:
            self._ts = time.time()
        else:
            self._ts = timestamp
        if payload is not None:
            self._payload = payload
            if len(payload) <= 8:
                self._fast_packet = False
            else:
                self._fast_packet = True
        else:
            self._payload = None


    @property
    def pgn(self):
        return self._pgn

    @property
    def prio(self):
        return self._prio

    @property
    def sa(self):
        return self._sa

    @property
    def da(self):
        return self._da

    @property
    def payload(self):
        return self._payload

    @property
    def fast_packet(self):
        return self._fast_packet

    @property
    def is_iso_protocol(self):
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
        pgn_def = PGNDefinitions.pgn_defs().pgn_def(self._pgn)
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
            pgn_def = PGNDefinitions.pgn_defs().pgn_def(self._pgn)
            name = pgn_def.name
        except N2KUnknownPGN:
            name = "Unknown PGN"
        if self._payload is None:
            payload = " "
        else:
            payload = self._payload.hex()
        return "PGN %d|%04X|%s sa=%d da=%d time=%s data:%s" % (self._pgn, self._pgn, name, self._sa, self._da,
                                                               format_timestamp(self._ts, self.ts_format), payload)

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

    def serialize(self):
        return MessageToJson(self.as_protobuf())

    def decode(self):
        try:
            pgn_def = PGNDefinitions.pgn_defs().pgn_def(self._pgn)
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

        rmsg = NMEA2000Msg(
            pgn=int(fields[0]),
            da=da,
            payload=base64.b64decode(fields[2])
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
        raise ValueError
    try:
        rmsg = decodePGDY(msg)
    except N2KRawDecodeError as e:
        _logger.error("PDGY sentence error: %s %s" % (e, str(msg)))
        raise
    _logger.debug("NMEA2000 message from PGDY:%s" % rmsg.format1())
    return rmsg


def fromPGNST(frame):
    raise NotImplementedError("PGNST decoding")


class NMEA2000Object:
    '''
    This class and subclasses hold decoded NMEA2000 entity that are directly processable
    The generic subclass is a default
    Specific subclasses can be created to handle special processing
    '''

    def __init__(self, pgn: int):
        self._pgn = pgn
        try:
            self._pgn_def = PGNDefinitions.pgn_definition(pgn)
        except N2KUnknownPGN:
            _logger.error("NMEA2000Object creation with unknown PGN %d" % pgn)
            raise
        self._sa = 0
        self._da = 0
        self._fields = None
        self._message = None
        self._prio = 7

    def from_message(self, msg: NMEA2000Msg):
        if self._pgn != msg.pgn:
            raise ValueError
        self._sa = msg.sa
        self._da = msg.da
        self._message = msg
        self._fields = msg.decode()['fields']
        self.update()
        return self

    def message(self):
        if self._message is None:
            self._message = NMEA2000Msg(self._pgn, self._prio, self._sa, self._da, self.encode_payload())
        if self._pgn_def.pdu_format == PGNDef.PDU1 and self._da == 0:
            _logger.warning("NMEA2000 Message with PDU1 format and no destination address")
        return self._message

    def update(self):
        raise NotImplementedError("Method update To be implemented in subclass")

    def encode_payload(self) -> bytes:
        raise NotImplementedError("Method encode_payload To be implemented in subclass")

    @property
    def pgn(self):
        return self._pgn

    @property
    def sa(self):
        return self._sa

    @property
    def fields(self) -> dict:
        return self._fields

    @sa.setter
    def sa(self, value):
        self._sa = value


#-----------------------------------------------------------------------------------
#
#   Set of classes to manage reassembly of Fast Packet messages payload
#
#-----------------------------------------------------------------------------------


class FastPacketException(Exception):
    pass


class FastPacket:
    '''
    This manage the reassembly for one NMEA2000 with payload > 8 bytes
    An instance is created each time a new sequence is detected
    '''

    @staticmethod
    def compute_key(pgn, addr, seq):
        return pgn + (addr << 16) + (seq << 24)

    def __init__(self, pgn, addr, seq):
        self._key = self.compute_key(pgn, addr, seq)
        self._source = addr
        self._seq = seq
        self._byte_length = 0
        self._length = 0
        self._pgn = pgn
        self._frames = {}
        self._count = 0
        self._nbframes = 0
        self._timestamp = time.time()

    def first_packet(self, frame):
        self._byte_length = frame[1]
        l7 = self._byte_length - 6
        nb7 = int(l7 / 7)
        if l7 % 7 != 0:
            nb7 += 1
        self._nbframes = nb7 + 1
        self._length += 6
        self._frames[0] = frame[2:]
        self._count += 1

    def add_packet(self, frame):
        counter = frame[0] & 0x1F

        try:
            fr = self._frames[counter]
            _logger.error("FastPacket duplicate frame for pgn %d addr %d seq %d index %d new:%s exist: %s" %
                          (self._pgn, self._source, self._seq, counter, frame.hex(), fr.hex()))
            raise FastPacketException("Frame Index duplicate %d" % counter)
        except KeyError:
            self._frames[counter] = frame[1:]
        self._count += 1
        self._length += len(frame) - 1

    def check_complete(self):
        if self._nbframes == 0:
            return False
        if self._length >= self._byte_length or self._count >= self._nbframes:
            return True
        else:
            return False

    def total_frame(self):
        result = bytearray(self._byte_length)
        start_idx = 0
        for i in range(0, self._nbframes):
            try:
                f = self._frames[i]
            except KeyError:
                _logger.error("Fast packet missing frame %d" % i)
                raise FastPacketException("Missing frame %d" % i)
            l = len(f)
            if start_idx + l >= self._byte_length:
                result[start_idx:] = f[:self._byte_length - start_idx + 1]
            else:
                result[start_idx:] = f
            start_idx += l
        return result

    def check_validity(self) -> bool:
        '''
        Check the validity of the current sequence to eliminate uncomplete sequences
        After a certain time
        :return:
        '''
        if self._nbframes > 0:
            if time.time() - self._timestamp < (0.01 * self._nbframes):
                return True
        return False

    @property
    def key(self):
        return self._key

    @property
    def pgn(self):
        return self._pgn


class FastPacketHandler:

    '''
    This class is linked to one Coupler instance and handle the reassembly of fast Packets payload

    '''

    def __init__(self, instrument):
        self._sequences = {}
        self._instrument = instrument
        self._write_sequences = {}

    def process_frame(self, pgn, addr, frame, trace=None):
        seq = (frame[0] >> 5) & 7
        key = FastPacket.compute_key(pgn, addr, seq)
        handle = self._sequences.get(key, None)
        counter = frame[0] & 0x1f
        _logger.debug("Fast Packet ==> PGN %d addr %d seq %d frame %s" % (pgn, addr, seq, frame.hex()))

        def allocate_handle():
            l_handle = FastPacket(pgn, addr, seq)
            self._sequences[l_handle.key] = l_handle
            _logger.debug(
                "Fast packet ==> start sequence on PGN %d from address %d with sequence %d" % (pgn, addr, seq))
            return l_handle

        if handle is None:
            handle = allocate_handle()

        if counter == 0:
            handle.first_packet(frame)
        else:
            handle.add_packet(frame)
        if handle.check_complete():
            result = handle.total_frame()
            self._sequences[key] = None
            _logger.debug("Fast packet ==> end sequence on PGN %d from address %d sequence %d" % (pgn, addr, seq))
            return result
        else:
            return None

    def is_pgn_active(self, pgn, addr, frame) -> bool:
        seq = (frame[0] >> 5) & 7
        key = FastPacket.compute_key(pgn, addr, seq)
        try:
            handle = self._sequences[key]
            return True
        except KeyError:
            return False

    def collect_garbage(self):
        to_be_removed = []
        for s in self._sequences.values():
            if not s.check_validity():
                to_be_removed.append(s.key)
        for key in to_be_removed:
            del self._sequences[key]

    def split_message(self, pgn, data) -> bytearray:
        '''
        split the NMEA payload with length > 8 with Fast Packet structure
        :param pgn:
        :param data: NMEA 2000 payload
        :return: iterator over Fast Packet frames
        '''
        nb_frames = ((len(data) - 6) / 7) + 1
        seq = self.allocate_seq(pgn)
        seq_en = seq << 5
        counter = 0
        total_len = len(data)
        # print("Fast packet split data  for PGN", pgn, "data len", total_len)
        data_ptr = 0
        while counter < nb_frames:
            remaining_bytes = total_len - data_ptr
            frame_len = min(8, remaining_bytes + 1)
            frame = bytearray(frame_len)
            frame[0] = seq_en | counter
            ptr = 1
            if counter == 0:
                frame[1] = total_len
                ptr += 1
            while ptr < frame_len:
                frame[ptr] = data[data_ptr]
                data_ptr += 1
                ptr += 1
            # print("frame #", counter, "remaining bytes", remaining_bytes, "DLC", len(frame))
            yield frame
            counter += 1
        self.free_seq(pgn, seq)

    def allocate_seq(self, pgn):
        seq = self._write_sequences.get(pgn, 0)
        if seq == 0:
            self._write_sequences[pgn] = 1
            return 1
        else:
            raise ValueError

    def free_seq(self, pgn, seq):
        self._write_sequences[pgn] = 0


class NMEA2000Writer(threading.Thread):
    '''
    This class implements the buffered write on CAN interface
    It handles the conversion towards the actual interface protocol
    Queuing of messages and throughput management

    '''

    def __init__(self, instrument, max_throughput):
        self._name = instrument.name() + '-Writer'
        _logger.info('Creating writer:%s' % self._name)
        super().__init__(name=self._name, daemon=True)
        self._instrument = instrument
        self._max_throughput = max_throughput
        self._queue = queue.Queue(80)
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
            delta = self._last_msg_ts - actual
            if delta < self._interval:
                time.sleep(self._interval - delta)
                actual = time.monotonic()
            self._last_msg_ts = actual
            self._instrument.send(msg)
            self._instrument.validate_n2k_frame(msg.raw)
        _logger.info("%s thread stops" % self._name)

    def stop(self):
        self._stop_flag = True
        self._queue.put(NavGenericMsg(NULL_MSG))
