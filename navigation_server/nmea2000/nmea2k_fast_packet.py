# -------------------------------------------------------------------------------
# Name:        nmea2k_fast_packet
# Purpose:     Handle fast packet protocol (transport layer) for NMEA2000
#
# Author:      Laurent Carré
#
# Created:     26/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import time
import math

_logger = logging.getLogger("ShipDataServer." + __name__)

#-----------------------------------------------------------------------------------
#
#   Set of classes to manage reassembly of Fast Packet messages payload
#
#-----------------------------------------------------------------------------------


class FastPacketException(Exception):
    pass


class FastPacket:
    """
    This manage the reassembly for one NMEA2000 with payload > 8 bytes
    An instance is created each time a new sequence is detected
    """

    __slots__ = ('_key', '_source', '_seq', '_byte_length', '_length', '_pgn', '_frames', '_count', '_nbframes',
                 '_timestamp')

    @staticmethod
    def compute_key(pgn, addr, seq) -> int:
        """
        input:
        pgn: on 20 bits maximum (17 so far)
        addr: source address on 8 bits
        seq: sequence number of the fats packet super frame on 3 (max 4) bits

        Return the key on 32 bits
        """
        return pgn + (addr << 20) + (seq << 28)

    def __init__(self, pgn, addr, seq):
        self._key = self.compute_key(pgn, addr, seq)
        self._source = addr
        self._seq = seq
        self._byte_length = 0
        self._length = 0
        self._pgn = pgn
        self._frames = {}
        self._count = 0
        self._nbframes = 0
        self._timestamp = time.time()

    def first_packet(self, frame):
        self._byte_length = frame[1]
        l7 = self._byte_length - 6
        nb7 = int(l7 / 7)
        if l7 % 7 != 0:
            nb7 += 1
        self._nbframes = nb7 + 1
        self._length += 6
        self._frames[0] = frame[2:]
        self._count += 1

    def add_packet(self, frame):
        counter = frame[0] & 0x1F

        try:
            fr = self._frames[counter]
            _logger.error("FastPacket duplicate frame for pgn %d addr %d seq %d index %d new:%s exist: %s" %
                          (self._pgn, self._source, self._seq, counter, frame.hex(), fr.hex()))
            raise FastPacketException("Frame Index duplicate %d" % counter)
        except KeyError:
            self._frames[counter] = frame[1:]
        self._count += 1
        self._length += len(frame) - 1

    def check_complete(self) -> bool:
        if self._nbframes == 0:
            return False
        if self._length >= self._byte_length or self._count >= self._nbframes:
            return True
        else:
            return False

    def total_frame(self) -> bytearray:
        result = bytearray(self._byte_length)
        start_idx = 0
        for i in range(0, self._nbframes):
            try:
                f = self._frames[i]
            except KeyError:
                _logger.error("Fast packet missing frame %d" % i)
                raise FastPacketException("Missing frame %d" % i)
            l = len(f)
            if start_idx + l >= self._byte_length:
                result[start_idx:] = f[:self._byte_length - start_idx + 1]
            else:
                result[start_idx:] = f
            start_idx += l
        return result

    def check_validity(self) -> bool:
        """
        Check the validity of the current sequence to eliminate uncomplete sequences
        After a certain time
        :return:
        """
        if self._nbframes > 0:
            if time.time() - self._timestamp < (0.01 * self._nbframes):
                return True
        return False

    @property
    def key(self):
        return self._key

    @property
    def pgn(self):
        return self._pgn


class FastPacketHandler:

    """
    This class is linked to one Coupler instance and handle the reassembly of fast Packets payload

    """

    def __init__(self, instrument):
        self._sequences = {}
        self._instrument = instrument
        self._write_sequences = {}

    def process_frame(self, pgn, addr, frame):
        seq = (frame[0] >> 5) & 7
        key = FastPacket.compute_key(pgn, addr, seq)
        handle = self._sequences.get(key, None)
        counter = frame[0] & 0x1f
        _logger.debug("Fast Packet ==> PGN %d addr %d seq %d frame %s" % (pgn, addr, seq, frame.hex()))

        def allocate_handle() -> FastPacket:
            l_handle = FastPacket(pgn, addr, seq)
            self._sequences[l_handle.key] = l_handle
            _logger.debug(
                "Fast packet ==> start sequence on PGN %d from address %d with sequence %d" % (pgn, addr, seq))
            return l_handle

        if handle is None:
            if counter != 0:
                raise FastPacketException(f"Fast packet PGN {pgn} from address {addr} wrong first packet {counter}")
            handle = allocate_handle()

        if counter == 0:
            handle.first_packet(frame)
        else:
            try:
                handle.add_packet(frame)
            except FastPacketException:
                del self._sequences[key]
                raise

        if handle.check_complete():
            del self._sequences[key]
            result = handle.total_frame()
            _logger.debug("Fast packet ==> end sequence on PGN %d from address %d sequence %d" % (pgn, addr, seq))
            return result
        else:
            return None

    def is_pgn_active(self, pgn, addr, frame) -> bool:
        seq = (frame[0] >> 5) & 7
        key = FastPacket.compute_key(pgn, addr, seq)
        try:
            handle = self._sequences[key]
            return True
        except KeyError:
            return False

    def collect_garbage(self):
        to_be_removed = []
        for s in self._sequences.values():
            if not s.check_validity():
                to_be_removed.append(s.key)
        for key in to_be_removed:
            del self._sequences[key]

    def split_message(self, pgn: int, data: bytearray):
        """
        split the NMEA payload with Fast Packet structure
        :param pgn:
        :param data: NMEA 2000 payload
        :return: iterator over Fast Packet frames
        """
        nb_frames = math.ceil((len(data) - 6) / 7) + 1  # corrected in 2.6.1
        seq = self.allocate_seq(pgn)
        seq_en = seq << 5
        counter = 0
        total_len = len(data)
        # _logger.debug(f"Fast packet split data  for PGN {pgn} data len {total_len} nb frames:{nb_frames}")
        data_ptr = 0
        while counter < nb_frames:
            remaining_bytes = total_len - data_ptr
            frame_len = min(8, remaining_bytes + 1)
            frame = bytearray(8)
            frame[0] = seq_en | counter
            ptr = 1
            if counter == 0:
                frame[1] = total_len
                ptr += 1
            while ptr < frame_len:
                frame[ptr] = data[data_ptr]
                data_ptr += 1
                ptr += 1
            if frame_len < 8:
                while ptr < 8:
                    frame[ptr] = 0xFF
                    ptr += 1
            # _logger.debug(f"{pgn} => frame # {counter} remaining bytes {remaining_bytes} DLC {len(frame)}")
            yield frame
            counter += 1
        self.free_seq(pgn, seq)

    def allocate_seq(self, pgn: int) -> int:
        """
        Allocate a sequence number for a given PGN. Currently one sequence at a time for a given PGN
        So seq is always 1
        """
        seq = self._write_sequences.get(pgn, 0)
        if seq != 0:
            _logger.warning(f"NMEA2000 Fast Packet sequence {seq} for PGN {pgn} already in use")
        self._write_sequences[pgn] = 1
        return 1


    def free_seq(self, pgn, seq):
        _logger.debug(f"Fast packet free sequence for PGN {pgn}")
        self._write_sequences[pgn] = 0

