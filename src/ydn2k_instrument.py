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
from generic_msg import NavGenericMsg, N2K_MSG, NULL_MSG

_logger = logging.getLogger("ShipDataServer")


class YDInstrument(BufferedIPInstrument):

    def __init__(self, opts):
        super().__init__(opts)
        self._separator = b'\r\n'
        self._separator_len = 2
        if self._mode == self.NMEA0183:
            self.set_message_processing()
        else:
            self._fast_packet_handler = FastPacketHandler(self)
            self.set_message_processing(msg_processing=self.frame_processing)

    def frame_processing(self, frame):
        _logger.debug("frame=%s" % frame)
        if frame[0] == 4:
            return NavGenericMsg(NULL_MSG)
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
        if self._fast_packet_handler.is_pgn_active(pgn, data):
            data = self._fast_packet_handler.process_frame(pgn, data)
            if data is None:
                raise ValueError # no error but just to escape
        elif PGNDefinitions.pgn_definition(pgn).fast_packet():
            self._fast_packet_handler.process_frame(pgn, data)
            raise ValueError  # no error but just to escape

        msg = NMEA2000Msg(pgn, prio, sa, 0, data)
        gmsg = NavGenericMsg(N2K_MSG, raw=frame, msg=msg)
        _logger.debug("YD PGN decode:%s" % str(msg))
        return gmsg




