#-------------------------------------------------------------------------------
# Name:        IP Coupler
# Purpose:     Abstract class for all instruments with a IP transport interface
#
# Author:      Laurent Carré
#
# Created:     04/04/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import queue

from nmea_routing.IPCoupler import BufferedIPCoupler
from nmea_routing.nmea2000_msg import NMEA2000Msg, FastPacketHandler
from nmea2000.nmea2k_pgndefs import PGNDefinitions, N2KUnknownPGN
from nmea_routing.generic_msg import NavGenericMsg, N2K_MSG, NULL_MSG, TRANSPARENT_MSG

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class YDCoupler(BufferedIPCoupler):

    def __init__(self, opts):
        super().__init__(opts)
        self._separator = b'\r\n'
        self._separator_len = 2
        if self._mode == self.NMEA0183:
            self.set_message_processing()
        else:
            self._fast_packet_handler = FastPacketHandler(self)
            self.set_message_processing(msg_processing=self.input_frame_processing)
            self._reply_queue = queue.Queue(5)

    def input_frame_processing(self, frame):
        _logger.debug("%s receive frame=%s" % (self._name, frame))
        if frame[0] == 4:
            return NavGenericMsg(NULL_MSG)
        fields = frame.split(b' ')
        data_len = len(fields) - 3
        if data_len <= 0:
            _logger.error("Invalid frame %s" % frame)
            raise ValueError
        if fields[1] == b'T':
            # reply on send
            _logger.debug("%s reply on send: %s" % (self._name, frame))
            try:
                self._reply_queue.put(frame, block=False)
            except queue.Full:
                _logger.critical("YD write feedback queue full")
            raise ValueError
        elif fields[1] != b'R':
            _logger.error("Invalid frame %s" % frame)
            raise ValueError
        pgn = int(fields[2][1:6], 16) & 0x3FFFF
        prio = (int(fields[2][0:2], 16) >> 2) & 7
        sa = int(fields[2][6:8], 16)
        data = bytearray(data_len)
        i = 0
        for db in fields[3:]:
            data[i] = int(db, 16)
            i += 1

        def check_pgn():
            try:
                fp = PGNDefinitions.pgn_definition(pgn).fast_packet()
            except N2KUnknownPGN:
                raise ValueError
            return fp

        if self._fast_packet_handler.is_pgn_active(pgn, sa, data):
            data = self._fast_packet_handler.process_frame(pgn, sa,  data)
            if data is None:
                raise ValueError # no error but just to escape
        elif check_pgn():
            self._fast_packet_handler.process_frame(pgn, sa, data)
            raise ValueError  # no error but just to escape

        msg = NMEA2000Msg(pgn, prio, sa, 0, data)
        gmsg = NavGenericMsg(N2K_MSG, raw=frame, msg=msg)
        _logger.debug("YD PGN decode:%s" % str(msg))
        return gmsg

    def encode_nmea2000(self, msg: NMEA2000Msg) -> NavGenericMsg:
        canid = b'%08X' % (msg.pgn << 8 | msg.prio << 26 | msg.da)

        def encode(data: bytearray):
            return NavGenericMsg(TRANSPARENT_MSG, raw=b'%s %s\r\n' % (canid, data.hex(b' ').encode()))
        if msg.fast_packet:
            for data_packet in self._fast_packet_handler.split_message(msg.pgn, msg.payload):
                yield encode(data_packet)
        else:
            yield encode(msg.payload)

    def validate_n2k_frame(self, frame):
        try:
            self._reply_queue.get(timeout=10.0)
            _logger.debug("YD Write OK:%s" % frame)
        except queue.Empty:
            _logger.error("YD write error on frame %s" % frame)







