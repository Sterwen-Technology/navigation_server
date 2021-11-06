
import operator
from functools import reduce
import datetime
import time


class NMEA0183Sentences:

    @staticmethod
    def checksum(nmea_str):
        return reduce( operator.xor, map(ord, nmea_str), 0)

    @staticmethod
    def hex_checksum(nmea_str):
        val = NMEA0183Sentences.checksum(nmea_str)
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
        print(" Local to UTC %d:%d" % (NMEA0183Sentences._local_hours, NMEA0183Sentences._local_minutes))

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




if __name__ == "__main__":

    print("=====================")
    NMEA0183Sentences.init("SN")
    s = ZDA()
    print(s.message())


