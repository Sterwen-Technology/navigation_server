#-------------------------------------------------------------------------------
# Name:        IP Coupler
# Purpose:     Abstract class for all instruments with a IP transport interface
#
# Author:      Laurent Carré
#
# Created:     27/02/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import socket
import logging
import queue
import threading
import time

from nmea2000.nmea2k_pgndefs import PGNDef, N2KUnknownPGN
from nmea_routing.generic_msg import *
from nmea_routing.coupler import Coupler, CouplerReadError, CouplerTimeOut
from nmea_routing.nmea0183 import process_nmea0183_frame, NMEAInvalidFrame, NMEA0183Msg
from nmea_routing.nmea2000_msg import fromProprietaryNmea, FastPacketException, NMEA2000Msg, FastPacketHandler

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


#################################################################
#
#   Classes for interfacing instruments over TCP or UDP
#
#################################################################


class IPCoupler(Coupler):
    '''
    abstract class for all couplers based on IP protocol communication
    '''
    def __init__(self, opts):
        super().__init__(opts)
        self._address = opts.get('address', str, 'localhost')
        self._port = opts.get('port', int, 0)
        self._buffer_size = opts.get('buffer_size', int, 256)

        self._protocol = opts.get('transport', str, 'TCP')
        if self._protocol == 'TCP':
            self._transport = TCP_reader(self._address, self._port, self._timeout, self._buffer_size)
        elif self._protocol == 'UDP':
            self._transport = UDP_reader(self._address, self._port, self._timeout, self._buffer_size)

    def open(self) -> bool:

        if self._transport.open():
            self._state = self.OPEN
            if self._protocol == 'TCP':
                self._state = self.CONNECTED
            return True
        else:
            self._state = self.NOT_READY
            return False

    def send(self, msg: NavGenericMsg):

        _logger.debug("%s Sending %s" % (self.name(), msg.printable()))
        if self._state == self.NOT_READY:
            _logger.error("Write attempt on non ready transport: %s" % self.name())
            return False
        if self._trace_msg:
            self.trace(self.TRACE_OUT, msg)
        return self._transport.send(msg.raw)

    def close(self):
        self._transport.close()
        self._state = self.NOT_READY

    def transport(self):
        return self._transport


class IP_transport:

    def __init__(self, address, port, timeout, buffer_size):
        self._address = address
        self._port = port
        self._ref = "%s:%d" % (self._address, self._port)
        self._socket = None
        self._timeout = timeout
        self._buffer_size = buffer_size

    def close(self):
        if self._socket is not None:
            self._socket.close()

    def ref(self):
        return self._ref


class UDP_reader(IP_transport):

    def __init__(self, address, port, timeout, buffer_size):
        super().__init__(address, port, timeout, buffer_size)

    def open(self):
        _logger.info("opening UDP port %d" % self._port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self._socket.bind(('', self._port))
        except OSError as e:
            _logger.error("Error opening UDP socket %s:%s" % (self._ref, str(e)))
            self._socket.close()
            return False
        self._socket.settimeout(self._timeout)

        return True

    def recv(self):
        try:
            data, address = self._socket.recvfrom(self._buffer_size)
        except OSError as e:
            raise CouplerReadError(e)
        # print(data)
        return data

    def send(self, msg):
        try:
            self._socket.sendto(msg, (self._address, self._port))
            return True
        except OSError as e:
            _logger.critical("Error writing on UDP socket %s: %s" % (self._ref, str(e)))
            self.close()
            return False


class TCP_reader(IP_transport):

    def __init__(self, address, port, timeout, buffer_size):
        super().__init__(address, port, timeout, buffer_size)

    def open(self):
        _logger.info("Connecting (TCP) to NMEA source %s" % self._ref)
        try:
            self._socket = socket.create_connection((self._address, self._port), 5.0)

            _logger.info("Successful TCP connection %s" % self._ref)
            self._socket.settimeout(self._timeout)
            return True
        except OSError as e:
            _logger.error("Connection error using TCP %s: %s" % (self._ref, str(e)))
            return False

    def recv(self):
        try:
            msg = self._socket.recv(self._buffer_size)
        except (TimeoutError, socket.timeout):
            _logger.info("Timeout error on TCP socket %s" % self._ref)
            raise CouplerTimeOut
        except socket.error as e:
            _logger.error("Error receiving from TCP socket %s: %s" % (self._ref, str(e)))
            raise CouplerReadError
        return msg

    def send(self, msg):
        _logger.debug("TCP send %s" % msg)
        try:
            self._socket.sendall(msg)
            return True
        except OSError as e:
            _logger.critical("Error writing to TCP socket %s: %s" % (self._ref, str(e)))
            return False


class IPAsynchReader(threading.Thread):
    '''
    This class provides asynchronous messages reassembly over IP protocol. Preferably TCP/IP to avoid messages loss
    It acts as an intermediate between the IP transport and the coupler.
    Communication is done via a queue in which complete messages are pushed
    ASCII based messages separated by delimiters, usually <CR><LF> for NMEA0183
    Messages delimiter is configurable
    The syntax analysis is performed by the _msg_processing configurable method. A ValueError exception is raised when
    Additional low level messages are needed to complete the message to process NMEA2000 FastPacket for instance.
    Transport errors, except timeout, lead to the push of a specific <EOF> messages indicating the end of the flow
    '''

    def __init__(self, coupler, out_queue, separator, msg_processing):
        super().__init__()
        if isinstance(coupler, IPCoupler):
            self._transport = coupler.transport()
            self._coupler = coupler
            self._cname = "Coupler %s" % coupler.name()
        else:
            self._transport = coupler
            self._coupler = None
            self._cname = "Transport %s" % self._transport.ref()

        self._out_queue = out_queue
        self._separator = separator
        self._msg_processing = msg_processing
        self._stop_flag = False
        self._buffer = bytearray(512)
        self._transparent = False

    def run(self):
        part = False
        part_buf = bytearray()
        while not self._stop_flag:
            try:
                buffer = self._transport.recv()
            except CouplerTimeOut:
                _logger.info("%s Asynchronous read transport time out" % self._cname)
                continue
            except CouplerReadError:
                break
            if self._transparent:
                msg = NavGenericMsg(TRANSPARENT_MSG, raw=buffer)
                self._out_queue.put(msg)
                continue
            # start buffer processing
            start_idx = 0
            end_idx = len(buffer)
            # _logger.debug("%s buffer length %d" % (self._transport.ref(), end_idx))
            if end_idx == 0:
                continue
            while True:
                if start_idx >= end_idx:
                    break
                index = buffer.find(self._separator, start_idx, end_idx)
                if index == -1:
                    if part:
                        #  there is continuity needed
                        if buffer[end_idx-1] in self._separator:
                            end_idx -= 1
                        part_buf.extend(buffer[start_idx:end_idx])
                        break
                    else:
                        _logger.debug("No separator found before end of buffer %s" % buffer[start_idx:end_idx])
                        if buffer[end_idx - 1] in self._separator:
                            # so in fact we have a full frame
                            end_idx -= 1
                            index = end_idx
                        else:

                            if buffer[start_idx] in self._separator:
                                start_idx += 1
                            if end_idx - start_idx > 0:
                                part = True
                                part_buf = bytearray(buffer[start_idx: end_idx])
                                _logger.debug("Partial frame (%d %d): %s" % (start_idx, end_idx, part_buf))
                            break
                if part:
                    _logger.debug("Existing partial buffer. New buffer index %d %s" % (start_idx, buffer))
                    if index - start_idx == 0:
                        frame = part_buf
                    else:
                        if buffer[start_idx] in self._separator:
                            start_idx += 1
                        frame = part_buf + buffer[start_idx:index]
                        _logger.debug("Frame reconstruction %s %s" % (part_buf, buffer[start_idx:index]))
                    part = False
                else:
                    if buffer[start_idx] in self._separator:
                        start_idx += 1
                    if index - start_idx <= 0:
                        _logger.debug("Null length frame on %s in %s" % (self._transport.ref(), buffer))
                        start_idx = index + 2
                        continue
                    frame = bytearray(buffer[start_idx:index])

                start_idx = index + 2
                if len(frame) == 0:
                    continue
                if self._coupler is not None:
                    self._coupler.trace_raw(Coupler.TRACE_IN, frame)
                try:
                    msg = self._msg_processing(frame)
                except ValueError:
                    continue
                except NMEAInvalidFrame:
                    _logger.error("Invalid frame in %s: %s %s" % (self._transport.ref(), frame, buffer))
                    continue
                try:
                    self._out_queue.put(msg, timeout=1.0)
                except queue.Full:
                    # _logger.critical("Asynchronous reader output Queue full for %s" % self._transport.ref())
                    # self._stop_flag = True
                    # break
                    _logger.error("Message overflow from %s lost 1 message" % self._transport.ref())
                    time.sleep(0.3)
                    continue
                if self._stop_flag:
                    break
        _logger.info("Asynch reader %s stopped" % self._transport.ref())
        self._stop_flag = True
        msg = self._msg_processing(bytes(b'\x04'))
        self._out_queue.put(msg)

    def stop(self):
        self._stop_flag = True

    def set_transparency(self, flag: bool):
        self._transparent = flag


class BufferedIPCoupler(IPCoupler):
    """
    This class provide a buffered input/output when there is a decoupling between read operation and the
    actual message read.
    This class cannot be instantiated from the Yaml
    Typical use:
    - Devices with multiple messages in a single I/O
    - N2K fast packet management
    """
    def __init__(self, opts):
        super().__init__(opts)

        self._in_queue = None
        self._asynch_io = None
        self._fast_packet_handler = None
        self._transparent = False
        self._msg_queue_size = opts.get('msg_queue_size', int, 50)

    def set_message_processing(self, separator=b'\r\n', msg_processing=process_nmea0183_frame):
        if self._direction != self.WRITE_ONLY:
            self._in_queue = queue.Queue(self._msg_queue_size)
            self._asynch_io = IPAsynchReader(self, self._in_queue, separator, msg_processing)

    def open(self) -> bool:
        if super().open():
            if self._state == self.CONNECTED and self._asynch_io is not None:
                self._asynch_io.start()
        else:
            return False

    def _read(self) -> NavGenericMsg:
        return self._in_queue.get()

    def stop(self):
        super().stop()
        if self._asynch_io is not None:
            if self._asynch_io.is_alive():
                self._asynch_io.stop()
                self._asynch_io.join()

    def set_transparency(self, flag: bool):
        if self._asynch_io is not None:
            self._asynch_io.set_transparency(flag)

    def mxpgn_decode(self, m0183: NMEA0183Msg) -> NavGenericMsg:
        '''
        Decode a NMEA0183 message encapsulating NMEA2000 in Shipmodul Miniplex format
        :param m0183: The NMEA0183 message from the Miniplex
        :return:
        A generic message encapsulating a NMEA2000 message
        Raise Value Error if the message is incomplete (Fast Packet)
        '''
        fields = m0183.fields()
        pgn = int(fields[0], 16)
        attribute = int(fields[1], 16)
        prio = attribute >> 12 & 7
        dlc = attribute >> 8 & 0xF
        source_addr = attribute & 0xFF
        pgn, dest_addr = PGNDef.pgn_pdu1_adjust(pgn)
        # now decide what to do next
        # if NMEA_MIX, return without decoding except for protocol messages when N2KController is present
        if self._mode == self.NMEA_MIX:
            if self._n2k_controller is None or not PGNDef.pgn_for_controller(pgn):
                # return a partially decoded NMEA2000 message
                msg = NMEA2000Msg(pgn, prio, source_addr, dest_addr)
                gmsg = NavGenericMsg(N2K_MSG, raw=m0183.raw, msg=msg)
                return gmsg
        # here we continue decoding
        data = bytearray(dlc)
        pr_byte = 0
        l_hex = len(fields[2])
        i_hex = l_hex - 2
        while pr_byte < dlc:
            data[pr_byte] = int(fields[2][i_hex:i_hex + 2], 16)
            pr_byte += 1
            i_hex -= 2

        # now the PGN sentence is decoded

        def check_pgn():
            try:
                fp = PGNDef.fast_packet_check(pgn)
            except N2KUnknownPGN as e:
                _logger.info("%s MXPGN decode %s SA=%d data=%s" % (self.name(), e, source_addr, data.hex()))
                raise ValueError
            return fp

        self.trace_n2k_raw(pgn, source_addr, prio, data)
        _logger.debug("start processing PGN %d" % pgn)
        if self._fast_packet_handler.is_pgn_active(pgn, source_addr, data):
            _logger.debug("Shipmodul PGN %d on address %d fast packet active" % (pgn, source_addr))
            try:
                data = self._fast_packet_handler.process_frame(pgn, source_addr, data, self.add_event_trace)
            except FastPacketException as e:
                _logger.error("Shipmodul Fast packet error %s pgn %d data %s" % (e, pgn, data.hex()))
                self.add_event_trace(str(e))
                raise ValueError
            if data is None:
                raise ValueError  # no error but just to escape
        elif check_pgn():
            _logger.debug("Shipmodul PGN %d is fast packet" % pgn)
            try:
                data = self._fast_packet_handler.process_frame(pgn, source_addr, data, self.add_event_trace)
            except FastPacketException as e:
                _logger.error("Shipmodul Fast packet error %s on initial frame pgn %d data %s" % (e, pgn, data.hex()))
                self.add_event_trace(str(e))
            raise ValueError  # no error but just to escape
        msg = NMEA2000Msg(pgn, prio, source_addr, dest_addr, data)
        _logger.debug("Shipmodul PGN decode:%s" % str(msg))  # very intensive => to be removed
        gmsg = NavGenericMsg(N2K_MSG, msg=msg)
        return gmsg


class TCPBufferedReader:
    '''
    This class implement buffered read of NMEA streams over IP for other interfaces than couplers
    Used to read commands issued by client towards the coupler via the server

    NOTE => To be moved to another module
    '''

    def __init__(self, connection, separator, address, msg_processing, buffer_size=128, timeout=10.):
        self._connection = connection
        self._connection.settimeout(timeout)
        self._buffer_size = buffer_size
        self._address = address
        self._ref = "%s:%d" % address
        self._in_queue = queue.Queue(50)
        self._reader = IPAsynchReader(self, self._in_queue, separator, msg_processing)
        self._reader.start()

    def read(self) -> NavGenericMsg:
        msg = self._in_queue.get()
        # self.trace(self.TRACE_IN, msg)
        return msg

    def stop(self):
        self._reader.stop()
        self._reader.join()
        _logger.info("TCP Buffered read stopped")

    def recv(self):
        start_time = time.monotonic()
        # _logger.info("TCPBufferedReader - start read to= %4.1f time=%f" % (self._connection.gettimeout(), start_time))
        try:
            msg = self._connection.recv(self._buffer_size)
        except (TimeoutError, socket.timeout):
            _logger.info("TCPBufferedReader - Timeout error on TCP socket duration %f" % (time.monotonic() - start_time))
            raise CouplerTimeOut()
        except socket.error as e:
            _logger.error("TCPBufferedReader - Error receiving from TCP socket %s: %s" % (self.name(), e))
            raise CouplerReadError()
        # _logger.info("TCPBufferedReader - read OK %d" % len(msg))
        return msg

    def name(self):
        return "TCPBufferedReader on %s:%d" % self._address

    def ref(self):
        return self._ref


class NMEATCPReader(BufferedIPCoupler):
    '''
    This class is implementing a generic NMEA reader that adapt to all known NMEA0183 based protocols
    NMEA2000 encapsulated in NMEA0183 are automatically converted to NMEA2000
    '''

    def __init__(self, opts):
        super().__init__(opts)
        self._direction = self.READ_ONLY  # no writing on generic reader
        self._fast_packet_handler = FastPacketHandler(self)
        self._separator = b'\r\n'
        self._separator_len = 2
        if self._mode != self.NMEA0183:
            self.set_message_processing(msg_processing=self.process_msg)
        else:
            self.set_message_processing()

    def process_msg(self, frame):

        if frame[0] == 4:
            return NavGenericMsg(NULL_MSG)
        msg0183 = NMEA0183Msg(frame)
        if msg0183.proprietary():
            return fromProprietaryNmea(msg0183)
        elif msg0183.address() == b'MXPGN':
            return self.mxpgn_decode(msg0183)
        else:
            return msg0183







