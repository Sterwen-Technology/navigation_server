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


class NMEA0183Sentences:

    @staticmethod
    def checksum(nmea_str):
        return reduce( operator.xor, map(ord, nmea_str[1:]), 0)

    @staticmethod
    def hex_checksum(nmea_str):
        val = NMEA0183Sentences.checksum(nmea_str[1:])
        hex_val = "%2X" % val
        return hex_val

    _sender_id = ''
    _local_hours = 0
    _local_minutes = 0

    @staticmethod
    def init(sender_id):
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


class XDR(NMEA0183Sentences):

    def __init__(self):
        self._sentence = "$%sXDR" % self._sender_id
        self._nbt = 0

    def add_transducer(self, t_type, data, unit, t_id):
        self._nbt += 1
        if self._nbt > 4:
            return
        self._sentence += ",%s,%s,%s,%s" % (t_type, data, unit, t_id)


class NMEA0183Filter:

    def __init__(self, filter_string, sep):
        self._formatters = []
        flist = filter_string.split(sep)
        for f in flist:
            if len(f) != 3:
                print('Invalid formatter', f)
                continue
            if type(f) == str:
                f = f.encode()
            self._formatters.append(f)

    def valid_sentence(self, msg):
        if msg[0] != ord('$') or msg[0] != ord('!'):
            print('Invalid NMEA message', msg[0])
            return False
        if msg[3:6] in self._formatters:
            return True
        else:
            return False


if __name__ == "__main__":

    print("=====================")
    NMEA0183Sentences.init("SN")
    s = ZDA()
    print(s.message())



