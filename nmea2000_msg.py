# Name:        nmea2000_msg
# Purpose:     Manages all NMEA2000/J1939 messages
#
# Author:      Laurent Carré
#
# Created:     26/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import time
import logging
from google.protobuf.json_format import MessageToJson
import json
import datetime

from nmea2k_pgndefs import *
from publisher import Publisher
from j1939_pb2 import j1939

_logger = logging.getLogger("ShipDataServer")


class J1939_msg:

    def __init__(self, pgn: int, prio: int, sa: int, da: int, payload: bytearray):
        self._pgn = pgn
        self._prio = prio
        self._sa = sa
        self._da = da
        self._payload = payload
        self._ts = time.time_ns()

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
        res = j1939()
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


class J1939Object:
    '''
    This class and subclasses hold decoded J1939 entity that are directly processable
    The generic subclass is a default
    Specific subclasses can be created to handle special processing
    '''

    def __init__(self, message: J1939_msg, fields: dict):
        self._msg = message
        self._fields = {}
        for f in fields:
            self._fields[f[0]] = f[1]


class SystemTime(J1939Object):

    secondsperday = 3600. * 24.

    def __init__(self, message, fields):
        super().__init__(message, fields)
        days = self._fields['Date']
        seconds = self._fields['Time']
        ts = (days * self.secondsperday) + seconds
        self._dt = datetime.datetime.fromtimestamp(ts)
        print(self._dt)


class J1939Factory:
    class_build = {
        126992: SystemTime
    }

    @staticmethod
    def build(message: J1939_msg, fields: dict) -> J1939Object:
        try:
            return J1939Factory.class_build[message.pgn](message, fields)
        except KeyError:
            return J1939Object(message, fields)
