#-------------------------------------------------------------------------------
# Name:        NMEA
# Purpose:      Utilities to analyse and generate NMEA sentences
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import operator
from functools import reduce
import datetime
import time
import logging

from nmea_routing.generic_msg import *
from generated.nmea0183_pb2 import nmea0183pb


_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NMEAInvalidFrame(Exception):
    pass


class NMEA0183Msg(NavGenericMsg):

    def __init__(self, data):
        super().__init__(N0183_MSG, raw=data, msg=self)
        # verify that we have a checksum
        if self._raw[self._datalen - 3] != ord('*'):
            _logger.error("NMEA183 Frame without checksum")
            raise NMEAInvalidFrame
        self._ts = int(time.monotonic() * 1e6)  # in microseconds
        self._checksum = int(self._raw[self._datalen-2:self._datalen], 16)
        if self._checksum != NMEA0183Sentences.b_checksum(self._raw[1:self._datalen - 3]):
            _logger.error("Checksum error %x %s" % (self._checksum, self._raw[:self._datalen].hex()))
            raise NMEAInvalidFrame
        ind_comma = self._raw.index(b',')
        self._datafields_s = ind_comma + 1
        self._address = self._raw[1: ind_comma]
        if self._address[0] == b'P':
            self._proprietary = True
        else:
            self._proprietary = False

    def talker(self):
        if not self._proprietary:
            return self._address[:2]
        else:
            raise ValueError

    def formatter(self):
        if not self._proprietary:
            return self._address[2:]
        else:
            raise ValueError

    def address(self):
        return self._address

    def proprietary(self):
        return self._proprietary

    def __str__(self):
        return self._raw[:self._datalen].decode()

    def replace_talker(self, talker: bytes):
        self._raw[1:3] = talker[:2]
        self._address[0:2] = talker[:2]

    def fields(self):
        return self._raw[self._datafields_s:self._datalen-3].split(b',')

    def as_protobuf(self, r: nmea0183pb) -> nmea0183pb:

        try:
            r.talker = self.talker().decode()
            r.formatter = self.formatter().decode()
        except ValueError:
            r.talker = self.address().decode()
        r.timestamp = self._ts
        # r.values.extend(self.fields())
        for f in self.fields():
            r.values.append(f.decode())
        return r


class NMEA0183SentenceMsg(NMEA0183Msg):

    def __init__(self, sentence):
        super().__init__(sentence.message())
        self._msg = sentence


def process_nmea0183_frame(frame):
    if frame[0] == 4:
        return NavGenericMsg(NULL_MSG)
    if frame[0] not in b'$!':
        raise NMEAInvalidFrame
    return NMEA0183Msg(frame)


class NMEA0183Sentences:

    @staticmethod
    def checksum(nmea_str: str):
        return reduce(operator.xor, map(ord, nmea_str[1:]), 0)

    @staticmethod
    def b_checksum(nmea_bytes: bytes):
        return reduce(operator.xor, nmea_bytes, 0)

    @staticmethod
    def hex_checksum(nmea_str):
        val = NMEA0183Sentences.checksum(nmea_str[1:])
        hex_val = "%2X" % val
        return hex_val

    _sender_id = b'XX'
    _local_hours = 0
    _local_minutes = 0

    @staticmethod
    def init(sender_id):
        if type(sender_id) == str:
            sender_id = sender_id.encode()
        NMEA0183Sentences._sender_id = sender_id
        NMEA0183Sentences._local_hours = time.timezone / 3600
        NMEA0183Sentences._local_minutes = time.timezone % 3600
        # print(" Local to UTC %d:%d" % (NMEA0183Sentences._local_hours, NMEA0183Sentences._local_minutes))

    def __init__(self):
        self._sentence = None

    def message(self):
        checksum = NMEA0183Sentences.checksum(self._sentence)
        msg = ("%s*%2X\r\n" % (self._sentence, checksum)).encode()
        return msg

    def talker(self):
        return self._sender_id

    def formatter(self):
        raise NotImplementedError


class ZDA(NMEA0183Sentences):

    def __init__(self, timestamp=0):
        if timestamp == 0:
            timestamp = datetime.datetime.utcnow()

        hms = timestamp.strftime("%H%M%S")
        cs = int(timestamp.microsecond / 1e4)
        dates = timestamp.strftime("%d,%m,%Y")
        self._sentence = "$%sZDA,%s.%2d,%s,%d,%d" % (NMEA0183Sentences._sender_id, hms, cs, dates,
                                                     NMEA0183Sentences._local_hours,
                                                     NMEA0183Sentences._local_minutes)

    def formatter(self):
        return b'ZDA'


class XDR(NMEA0183Sentences):

    def __init__(self):
        self._sentence = "$%sXDR" % self._sender_id
        self._nbt = 0

    def add_transducer(self, t_type, data, unit, t_id):
        self._nbt += 1
        if self._nbt > 4:
            return
        self._sentence += ",%s,%s,%s,%s" % (t_type, data, unit, t_id)

    def formatter(self):
        return b'XDR'


if __name__ == "__main__":

    print("=====================")
    NMEA0183Sentences.init("SN")
    s = ZDA()
    print(s.message())



