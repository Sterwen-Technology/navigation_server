#-------------------------------------------------------------------------------
# Name:        IP Coupler
# Purpose:     Abstract class for all instruments with a IP transport interface
#
# Author:      Laurent Carré
#
# Created:     04/04/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import queue

from nmea_routing.IPCoupler import BufferedIPCoupler
from nmea2000.nmea2000_msg import NMEA2000Msg, FastPacketHandler, FastPacketException
from nmea2000.nmea2k_pgndefs import PGNDefinitions, N2KUnknownPGN
from nmea_routing.generic_msg import NavGenericMsg, N2K_MSG, NULL_MSG, TRANSPARENT_MSG
from nmea_routing.coupler import IncompleteMessage

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



    @staticmethod
    def decode_frame(coupler, frame, pgn_white_list=None):
        _logger.debug("%s receive frame=%s" % (coupler.name(), frame))
        if frame[0] == 4:
            return NavGenericMsg(NULL_MSG)
        # coupler._total_msg_raw += 1
        coupler.increment_msg_raw()
        fields = frame.split(b' ')
        data_len = len(fields) - 3
        if data_len <= 0:
            _logger.error("YDCoupler - Invalid frame %s" % frame)
            raise IncompleteMessage

        def decode_msgid(msgid):
            pgn = int(msgid[1:6], 16) & 0x3FFFF
            prio = (int(msgid[0:2], 16) >> 2) & 7
            sa = int(msgid[6:8], 16)
            return pgn, prio, sa

        pgn, prio, sa = decode_msgid(fields[2])

        if pgn_white_list is not None:
            if pgn not in pgn_white_list:
                raise IncompleteMessage

        if fields[1] == b'T':
            # reply on send
            if coupler.n2k_writer is None:
                # there should be no send
                if pgn not in [60159, 61183, 61236, 126996]:
                    _logger.error("YD Coupler unexpected reply from %d pgn:%d %s" % (sa, pgn, frame))
                    raise IncompleteMessage
            else:
                _logger.debug("%s reply on send: %s" % (coupler.name(), frame))
                try:
                    coupler._reply_queue.put(frame, block=False)
                except queue.Full:
                    _logger.critical("YD write feedback queue full")
                    raise IncompleteMessage
        elif fields[1] != b'R':
            _logger.error("YDCoupler - Invalid frame %s" % frame)
            raise IncompleteMessage

        # pgn, prio, sa = decode_msgid(fields[2])

        data = bytearray(data_len)
        i = 0
        for db in fields[3:]:
            data[i] = int(db, 16)
            i += 1

        def check_pgn():
            try:
                fp = PGNDefinitions.pgn_definition(pgn).fast_packet()
            except N2KUnknownPGN:
                raise IncompleteMessage
            return fp

        if coupler.fast_packet_handler.is_pgn_active(pgn, sa, data):
            try:
                data = coupler.fast_packet_handler.process_frame(pgn, sa, data)
            except FastPacketException as e:
                _logger.error("YDCoupler Fast packet error %s pgn %d sa %d data %s" % (e, pgn, sa, data.hex()))
                coupler.add_event_trace(str(e))
                raise IncompleteMessage
            if data is None:
                raise IncompleteMessage  # no error but just to escape
        elif check_pgn():
            coupler.fast_packet_handler.process_frame(pgn, sa, data)
            raise IncompleteMessage  # no error but just to escape

        msg = NMEA2000Msg(pgn, prio, sa, 0, data)
        gmsg = NavGenericMsg(N2K_MSG, raw=frame, msg=msg)
        _logger.debug("YD PGN decode:%s" % str(msg))
        return gmsg

    def input_frame_processing(self, frame):
        return YDCoupler.decode_frame(self, frame)

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

    def send(self, msg):
        _logger.debug("YD N2K Write %s" % msg.printable())
        super().send(msg)







