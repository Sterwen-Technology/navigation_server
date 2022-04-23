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

from instrument import Instrument
from IPInstrument import BufferedIPInstrument
from nmea2000_msg import NMEA2000Msg, FastPacketHandler, FastPacketException
from nmea2k_pgndefs import PGNDefinitions
from nmea0183 import process_nmea0183_frame

_logger = logging.getLogger("ShipDataServer")


class YDInstrument(BufferedIPInstrument):

    def __init__(self, opts):
        super().__init__(opts)
        if self._mode == self.NMEA0183:
            self.set_message_processing()
        else:
            self.set_message_processing(self.frame_processing)

    @staticmethod
    def frame_processing(frame):
        _logger.debug("frame=%s" % frame)
        fields = frame.split(b' ')
        data_len = len(fields) - 3
        if data_len <= 0:
            _logger.error("Invalid frame %s" % frame)
            raise ValueError
        if fields[1] != b'R':
            _logger.error("Invalid frame %s" % frame)
            raise ValueError
        pgn = int(fields[2][1:6], 16) & 0x3FFFF
        prio = (int(fields[2][0:2], 16) >> 2) & 7
        sa = int(fields[2][6:8], 16)
        data = bytearray(data_len)
        i = 0
        for db in fields[3:]:
            data[i] = int(db,16)
            i += 1
        if FastPacketHandler.is_pgn_active(pgn):
            data = FastPacketHandler.process_frame(pgn, data)
            if data is None:
                raise ValueError # no error but just to escape
        elif PGNDefinitions.pgn_definition(pgn).fast_packet():
            FastPacketHandler.process_frame(pgn, data)
            raise ValueError  # no error but just to escape

        msg = NMEA2000Msg(pgn, prio, sa, 0, data)
        _logger.debug("YD PGN decode:%s" % str(msg))
        return msg




