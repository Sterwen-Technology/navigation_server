#-------------------------------------------------------------------------------
# Name:        IP Instrument
# Purpose:     Abstract class for all instruments with a IP transport interface
#
# Author:      Laurent Carré
#
# Created:     04/04/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
from instrument import InstrumentReadError, InstrumentTimeOut
from IPInstrument import IPInstrument, BufferedIPInstrument
from nmea2000_msg import NMEA2000Msg

_logger = logging.getLogger("ShipDataServer")


class YDInstrument(BufferedIPInstrument):

    def __init__(self, opts):
        super().__init__(opts, b'\r\n', self.frame_processing)

    @staticmethod
    def frame_processing(frame):
        _logger.debug("frame=%s" % frame)
        fields = frame.split(b' ')
        data_len = len(fields) - 3
        if data_len <= 0:
            _logger.error("Invalid frame")
            raise ValueError
        if fields[1] != b'R':
            _logger.error("Invalid frame")
            raise ValueError
        pgn = int(fields[2][1:6], 16) & 0x3FFFF
        prio = (int(fields[2][0:2], 16) >> 2) & 7
        sa = int(fields[2][6:8], 16)
        data = bytearray (data_len)
        i = 0
        for db in fields[3:]:
            data[i] = int(db,16)
            i += 1
        msg = NMEA2000Msg(pgn, prio, sa, 0, data)
        # _logger.debug("YD PGN decode:%s" % str(msg))
        return msg




