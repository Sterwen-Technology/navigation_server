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

from nmea2k_pgndefs import *
from publisher import Publisher
from src.nmea2000_pb2 import nmea2000

_logger = logging.getLogger("ShipDataServer")


class NMEA2000Msg:

    def __init__(self, pgn: int, prio: int = 0, sa: int = 0, da: int = 0, payload: bytearray = None):
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
        res.timestamp = int(self._ts / 1000)
        res.payload = self._payload
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

    def process_msg(self, msg):
        # print("Process msg pgn", msg.pgn)
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
        pgn_filter = opts.get('filter', None)
        if pgn_filter is not None:
            self._filter = pgn_list(pgn_filter)
        else:
            self._filter = None
        self._print_option = opts.get('print', 'ALL')

    def process_msg(self, msg):
        res = msg.decode()
        if self._print_option == 'NONE':
            return True
        if self._filter is not None:
            if msg.pgn not in self._filter:
                return True
        if res is not None:
            print(res)
        return True


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
