#-------------------------------------------------------------------------------
# Name:        raw_log_coupler
# Purpose:     Class implement a coupler (simulator) based on raw logs
#
# Author:      Laurent Carré
#
# Created:     23/07/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import logging
import threading
import queue
import time

from .raw_log_reader import RawLogFile, LogReadError
from router_core import Coupler, CouplerOpenRefused
from router_common import IncompleteMessage
from router_core import NMEA0183Msg, NMEAInvalidFrame
from router_core import fromProprietaryNmea, NMEA2000Msg
from nmea2000 import FastPacketHandler, FastPacketException
from nmea2000_datamodel import PGNDef
from router_common import NavGenericMsg, NULL_MSG, N2K_MSG
from couplers import ShipModulInterface
from couplers import YDCoupler

_logger = logging.getLogger("ShipDataServer."+__name__)


class AsynchLogReader(threading.Thread):

    def __init__(self, out_queue, process_message):
        super().__init__(daemon=True)
        self.name = "AsynchLogReader"
        self._logfile = None
        self._out_queue = out_queue
        self._stop_flag = False
        self._suspend_flag = False
        self._suspend_date = 0.0
        self._process_message = process_message

    def open(self, logfile):
        self._logfile = logfile

    def stop(self):
        self._stop_flag = True

    def suspend(self):
        self._suspend_flag = True
        self._suspend_date = time.time()

    def resume(self):
        delta = time.time() - self._suspend_date
        self._logfile.shift_start_replay(delta)
        self._suspend_flag = False

    def run(self):

        while not self._stop_flag:
            if self._suspend_flag:
                time.sleep(0.5)
                continue
            try:
                frame = self._logfile.read_message()
            except LogReadError as err:
                if err.reason == "EOF":
                    _logger.info("Log Coupler End of file")
                else:
                    _logger.error("LogCoupler error in message index=%d msg:%s" %
                                  (self._logfile.index,
                                   err.reason))
                self._out_queue.put(NavGenericMsg(NULL_MSG))
                break

            try:
                msg = self._process_message(frame)
            except IncompleteMessage:
                continue
            self._out_queue.put(msg)


class RawLogCoupler(Coupler):

    def __init__(self, opts):
        super().__init__(opts)
        self._filename = opts.get('logfile', str, None)
        self._direction = self.READ_ONLY
        if self._filename is None:
            raise ValueError
        self._logfile = None

        # need to initialize NMEA2000 decoding
        self._fast_packet_handler = FastPacketHandler(self)
        self._in_queue = None
        self._reader = None
        self._max_attempt = 1  # never retry
        # filters
        pgn_white_list = opts.getlist('pgn_white_list', int)
        if pgn_white_list is not None and len(pgn_white_list) > 0:
            self._pgn_white_list = pgn_white_list
        else:
            self._pgn_white_list = None

    def open(self):
        _logger.info("LogCoupler %s opening log file %s" % (self.object_name(), self._filename))
        if self._logfile is not None:
            # we can't reopen a file
            raise CouplerOpenRefused

        try:
            self._logfile = RawLogFile(self._filename)
        except IOError:
            return False

        self._in_queue = queue.SimpleQueue()
        if self._logfile.file_type == "ShipModulInterface":
            if self._mode == self.NMEA0183:
                self._reader = AsynchLogReader(self._in_queue, self.process_nmea0183)
            else:
                self._reader = AsynchLogReader(self._in_queue, self.process_n2k)
        elif self._logfile.file_type == "YDCoupler":
            self._reader = AsynchLogReader(self._in_queue, self.process_yd_frame)
        elif self._logfile.file_type == "SocketCANInterface":
            self._reader = AsynchLogReader(self._in_queue, self.process_can_frame)

        self._reader.open(self._logfile)
        self._state = self.OPEN
        self._logfile.prepare_read()
        self._reader.start()
        self._state = self.CONNECTED
        _logger.info("LogCoupler %s ready" % self.object_name())
        return True

    def close(self):
        self._state = self.NOT_READY
        if self._reader is not None:
            self._reader.stop()
            self._reader.join()

    def stop(self):
        super().stop()
        self.close()

    def _read(self):
        self._total_msg_raw += 1
        return self._in_queue.get()

    def _suspend(self):
        self._reader.suspend()

    def _resume(self):
        self._reader.resume()

    def process_shipmodul_frame(self, frame):
        try:
            msg0183 = NMEA0183Msg(frame)
        except ValueError:
            _logger.error("LogCoupler error in message or end of file index=%d date:%s msg:%s" %
                          (self._logfile.index,
                           self._logfile.get_current_log_date(),
                           self._logfile.message(self._logfile.index)))
            return NavGenericMsg(NULL_MSG)

        except NMEAInvalidFrame:
            _logger.error("LogCoupler InvalidFrame in message index=%d date:%s msg:%s" %
                          (self._logfile.index,
                           self._logfile.get_current_log_date(),
                           self._logfile.message(self._logfile.index)))
            raise IncompleteMessage
        return msg0183

    def process_nmea0183(self, frame):
        msg = self.process_shipmodul_frame(frame)
        return msg

    def process_n2k(self, frame):
        msg0183 = self.process_shipmodul_frame(frame)
        if msg0183.proprietary():
            return fromProprietaryNmea(msg0183)
        elif msg0183.address() == b'MXPGN':
            msg = ShipModulInterface.mxpgn_decode(self, msg0183)
            # print(msg.dump())
            return msg
        else:
            return msg0183

    def process_yd_frame(self, frame):
        msg = YDCoupler.decode_frame(self, frame, self._pgn_white_list)
        return msg

    def process_can_frame(self, frame):

        try:
            can_id = int(frame[:8], 16)
            data = bytearray.fromhex(frame[9:])
        except ValueError:
            _logger.error("Log coupler => erroneous frame:%s" % frame)
            raise IncompleteMessage

        pgn, da = PGNDef.pgn_pdu1_adjust((can_id >> 8) & 0x1FFFF)
        sa = can_id & 0xFF
        if self._pgn_white_list is not None:
            if pgn not in self._pgn_white_list:
                raise IncompleteMessage
        prio = (can_id >> 26) & 0x7
        # Fast packet handling
        if self._fast_packet_handler.is_pgn_active(pgn, sa, data):
            try:
                data = self._fast_packet_handler.process_frame(pgn, sa, data)
            except FastPacketException as e:
                _logger.error("CAN interface Fast packet error %s pgn %d sa %d data %s" % (e, pgn, sa, data.hex()))
                raise IncompleteMessage
            if data is None:
                raise IncompleteMessage
        else:
            if PGNDef.fast_packet_check(pgn):
                self._fast_packet_handler.process_frame(pgn, sa, data)
                raise IncompleteMessage
        # end fast packet handling
        n2k_msg = NMEA2000Msg(pgn, prio, sa, da, data)
        if n2k_msg is not None:
            return NavGenericMsg(N2K_MSG, msg=n2k_msg)
        else:
            raise IncompleteMessage

    def log_file_characteristics(self) -> dict:
        if self._state is self.NOT_READY:
            return None

        return {'start_date': self._logfile.start_date(),
                'end_date': self._logfile.end_date(),
                'nb_records': self._logfile.nb_records(),
                'duration': self._logfile.duration(),
                'filename': self._logfile.filename()
                }

    def current_log_date(self):
        if self._state == self.ACTIVE:
            return {'current_date': self._logfile.get_current_log_date()}

    def move_index(self, args):
        if self._state == self.ACTIVE:
            delta_t = args.get('delta', None)
            if delta_t is not None:
                self._logfile.move_forward(delta_t)

    def move_to_date(self, args):
        if self._state == self.ACTIVE:
            target_date = args.get('target_date', None)
            _logger.info("LogReader move to target date: %s" % target_date)
            if target_date is not None:
                self._logfile.move_to_date(target_date)

    def restart(self):
        if self._state == self.ACTIVE:
            _logger.info("RawLogCoupler restart from the beginning")
            self._logfile.restart()
