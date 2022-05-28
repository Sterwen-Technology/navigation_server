#-------------------------------------------------------------------------------
# Name:        nmea2000_msg
# Purpose:     Manages all NMEA2000 messages internal representation
#
# Author:      Laurent Carré
#
# Created:     26/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import time
from google.protobuf.json_format import MessageToJson
import datetime
import os

from nmea2k_pgndefs import *
from publisher import Publisher
from nmea2000_pb2 import nmea2000
from generic_msg import *
from configuration import NavigationConfiguration

_logger = logging.getLogger("ShipDataServer"+".nmea200msg")
# _logger.setLevel(logging.DEBUG)


class NMEA2000Msg:

    def __init__(self, pgn: int, prio: int = 0, sa: int = 0, da: int = 0, payload: bytes = None):
        self._pgn = pgn
        self._prio = prio
        self._sa = sa
        self._da = da
        if payload is not None:
            self._payload = payload
            self._ts = time.time_ns()
            if len(payload) <= 8:
                self._fast_packet = False
            else:
                self._fast_packet = True

    @property
    def pgn(self):
        return self._pgn

    def display(self):
        pgn_def = PGNDefinitions.pgn_defs().pgn_def(self._pgn)
        print("PGN %d|%04X|%s|time:%d" % (self._pgn, self._pgn, pgn_def.name,self._ts))

    def __str__(self):
        if self._pgn == 0:
            return "Dummy PGN 0"
        else:
            pgn_def = PGNDefinitions.pgn_defs().pgn_def(self._pgn)
            return "PGN %d|%04X|%s sa=%d time=%d data:%s" % (self._pgn, self._pgn, pgn_def.name, self._sa, self._ts,
                                                             self._payload.hex())

    def as_protobuf(self):
        res = nmea2000()
        res.pgn = self._pgn
        res.priority = self._prio
        res.sa = self._sa
        try:
            val = int(self._ts / 1000)
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
        pgn_def = PGNDefinitions.pgn_defs().pgn_def(self._pgn)
        try:
            return pgn_def.decode_pgn_data(self._payload)
        except N2KDecodeException as e:
            _logger.error("%s ignoring" % str(e))
            return None


class PgnRecord:

    def __init__(self, pgn: int, clock: int):
        self._pgn = pgn
        self._pgn_def = PGNDefinitions.pgn_defs().pgn_def(pgn)
        self._clock = clock
        self._count = 1

    @property
    def pgn(self):
        return self._pgn

    @property
    def pgn_def(self):
        return self.pgn_def

    def tick(self):
        self._count += 1

    def check(self, clock, interval) -> bool:
        if clock - self._clock >= interval:
            self._clock = clock
            return True
        else:
            return False

    def __str__(self):
        if self._pgn == 0:
            return "Dummy PGN 0"
        else:
            return "PGN %d|%04X|%s|count:%d" % (self._pgn, self._pgn, self._pgn_def, self._count)


class N2KProbePublisher(Publisher):

    def __init__(self, opts):
        _logger.info("Instantiating N2KProbePublisher")
        self._interval = int(opts['interval']) * 1e9
        self._records = {}
        super().__init__(opts)

    def process_msg(self, gen_msg):
        # print("Process msg pgn", msg.pgn)
        if gen_msg.type != N2K_MSG:
            return
        msg = gen_msg.msg
        clock = time.time_ns()
        display = False
        if msg.pgn == 0:
            return False
        try:
            rec = self._records[msg.pgn]
        except KeyError:
            display = True
            rec = PgnRecord(msg.pgn, clock)
            self._records[msg.pgn] = rec
        else:
            rec.tick()
            if rec.check(clock, self._interval):
                display = True
        if display:
            print(rec)
        return True

    def dump_records(self):
        for rec in self._records.values():
            print(rec)


class N2KTracePublisher(Publisher):

    def __init__(self, opts):
        super().__init__(opts)
        self._filter = opts.getlist('filter', int, None)
        _logger.info("%s filter:%s" % (self.name(), self._filter))
        self._print_option = opts.get('output', str, 'ALL')
        _logger.info("%s output option %s" % (self.name(), self._print_option))
        self._trace_fd = None
        filename = opts.get('file', str, None)
        if filename is not None:
            trace_dir = NavigationConfiguration.get_conf().get_option('trace_dir', '/var/log')
            date_stamp = datetime.datetime.now().strftime("%y%m%d-%H%M")
            filename = "%s-N2K-%s.log" % (filename, date_stamp)
            filepath = os.path.join(trace_dir, filename)
            _logger.info("Opening trace file %s" % filepath)
            try:
                self._trace_fd = open(filepath, "w")
            except IOError as e:
                _logger.error("Trace file error %s" % e)
                self._trace_fd = None

    def process_msg(self, gen_msg):
        if gen_msg.type != N2K_MSG:
            return True
        msg = gen_msg.msg
        if self._print_option == 'NONE':
            return True
        if self._filter is not None:
            if msg.pgn not in self._filter:
                return True
        # print("decoding %s", msg)
        res = msg.decode()
        # _logger.debug("Trace publisher msg:%s" % res)
        if res is not None:
            if self._print_option in ('ALL', 'PRINT'):
                print(res)
            if self._print_option in ('ALL', 'FILE') and self._trace_fd is not None:
                self._trace_fd.write(str(res))
                self._trace_fd.write('\n')
        return True

    def stop(self):
        if self._trace_fd is not None:
            self._trace_fd.close()
        super().stop()


def pgn_list(str_filter):
    res = []
    str_pgn_list = str_filter.split(',')
    pgn_defs = PGNDefinitions.pgn_defs()
    for str_pgn in str_pgn_list:
        pgn = int(str_pgn)
        try:
            pgn_d = pgn_defs.pgn_def(pgn)
        except KeyError:
            print("Invalid PGN:", pgn, "Ignored")
            continue
        res.append(pgn)
    return res


class NMEA2000Object:
    '''
    This class and subclasses hold decoded NMEA2000 entity that are directly processable
    The generic subclass is a default
    Specific subclasses can be created to handle special processing
    '''

    def __init__(self, pgn: int, message: NMEA2000Msg = None, **kwargs):
        self._pgn = pgn
        self._msg = message
        self.__dict__.update(kwargs)


class SystemTime(NMEA2000Object):

    secondsperday = 3600. * 24.

    def __init__(self, message, **kwargs):
        super().__init__(126992, message, **kwargs)
        if message is not None:
            self._days = message['Date']
            self._seconds = message['Time']
            ts = (self._days * self.secondsperday) + self._seconds
            self._dt = datetime.datetime.fromtimestamp(ts)
        # print(self._dt)


class NMEA2000Factory:
    class_build = {
        126992: SystemTime
    }

    @staticmethod
    def build(message: NMEA2000Msg, fields: dict) -> NMEA2000Object:
        try:
            return NMEA2000Factory.class_build[message.pgn](message, kwargs=fields)
        except KeyError:
            return NMEA2000Object(message.pgn, message, kwargs=fields)


class FastPacketException(Exception):
    pass


class FastPacket:

    def __init__(self, pgn, seq ):
        self._sequence = seq
        self._byte_length = 0
        self._length = 0
        self._pgn = pgn
        self._frames = {}
        self._count = 0
        self._nbframes = 0

    def first_packet(self, frame):
        self._byte_length = frame[1]
        l7 = self._byte_length - 6
        nb7 = int(l7/7)
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
            _logger.error("FastPacket duplicate frame index %d %s" % (counter, fr.hex()))
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
                result[start_idx:] = f[:self._byte_length - start_idx +1]
            else:
                result[start_idx:] = f
            start_idx += l
        return result

    @property
    def sequence(self):
        return self._sequence

    @property
    def pgn(self):
        return self._pgn


class FastPacketHandler:

    def __init__(self, instrument):
        self._sequences = [None for i in range(8)]
        self._pgn_active = {}
        self._instrument = instrument

    def process_frame(self, pgn, frame, trace=None):
        seq = (frame[0] >> 5) & 7
        handle = self._sequences[seq]
        counter = frame[0] & 0x1f
        _logger.debug("Fast Packet ==> PGN %d seq %d frame %s" % (pgn, seq, frame.hex()))
        if handle is None:
            # new sequence
            handle = FastPacket(pgn, seq)
            self._sequences[seq] = handle
            self._pgn_active[pgn] = True
            _logger.debug("Fast packet ==> start sequence on PGN %d with sequence %d" % (pgn, seq))
        else:
            if handle.pgn != pgn:
                _logger.error("Fast Packet PGN mix expected %d actual %d for seq %d" %
                              (handle.pgn, pgn, seq))
                raise FastPacketException("PGN mix on sequence %d: %d/%d" % (seq, handle.pgn, pgn))
            # we have a new fast packet sequence

        if counter == 0:
            handle.first_packet(frame)
        else:
            handle.add_packet(frame)
        if handle.check_complete():
            result = handle.total_frame()
            self._sequences[seq] = None
            self._pgn_active[pgn] = False
            _logger.debug("Fast packet ==> end sequence on PGN %d" % pgn)
            return result
        else:
            return None

    def is_pgn_active(self, pgn, frame) -> bool:
        seq = (frame[0] >> 5) & 7
        handle = self._sequences[seq]
        if handle is not None:
            if handle.pgn == pgn:
                return True
        return False









