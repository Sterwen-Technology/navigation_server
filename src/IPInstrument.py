#-------------------------------------------------------------------------------
# Name:        IP Instrument
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
from generic_msg import *
from instrument import Instrument, InstrumentReadError, InstrumentTimeOut
from nmea0183 import process_nmea0183_frame, NMEAInvalidFrame

_logger = logging.getLogger("ShipDataServer")


#################################################################
#
#   Classes for ShipModule interface
#################################################################


class IPInstrument(Instrument):

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

    def open(self):

        if self._transport.open():
            self._state = self.OPEN
            if self._protocol == 'TCP':
                self._state = self.CONNECTED
        else:
            self._state = self.NOT_READY

    def read(self):
        raw = self._transport.recv()
        # print(self._mode,raw)
        if self._mode == self.NMEA0183:
            msg = NavGenericMsg(N0183_MSG, raw=raw)
        else:
            raise InstrumentReadError("Protocol not supported")
        if self._trace_msg:
            self.trace(self.TRACE_IN, msg)
        return msg

    def send(self, msg):
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
            raise InstrumentReadError(e)
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
            raise InstrumentTimeOut
        except socket.error as e:
            _logger.error("Error receiving from TCP socket %s: %s" % (self._ref, str(e)))
            raise InstrumentReadError
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

    def __init__(self, instrument, out_queue, separator, msg_processing):
        super().__init__()
        if isinstance(instrument, IPInstrument):
            self._transport = instrument.transport()
            self._instrument = instrument
        else:
            self._transport = instrument
            self._instrument = None

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
            except InstrumentTimeOut:
                _logger.info("Asynchronous read transport time out")
                continue
            except InstrumentReadError:
                break
            if self._transparent:
                msg = NavGenericMsg(TRANSPARENT_MSG, raw=buffer)
                self._out_queue.put(msg)
                continue
            # start buffer processing
            start_idx = 0
            end_idx = len(buffer)
            _logger.debug("%s buffer length %d" % (self._transport.ref(), end_idx))
            if end_idx == 0:
                continue
            while True:
                if start_idx >= end_idx:
                    break
                index = buffer.find(self._separator, start_idx, end_idx)
                if index == -1:
                    if part:
                        #  there is contnuity needed
                        if buffer[end_idx-1] in self._separator:
                            end_idx -= 1
                        part_buf.extend(buffer[start_idx:end_idx])
                        break
                        #else:
                            #_logger.error("Frame missing delimiter start %d end %d" % (start_idx, end_idx))
                            #_logger.error("Frame missing delimiter %s" % buffer[start_idx: end_idx].hex(' ', 2))
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
                        #if buffer[index - 2] in self._separator:
                            #index -= 1
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
                    '''
                    try:
                        if frame[0] not in b'!$':
                            _logger.error("Invalid frame in %s: %s" % (self._transport.ref(), frame))
                            _logger.error("start %d last %d buffer %s" % (start_idx, index, buffer))
                    except IndexError:
                        _logger.error("Null Frame %s start %d end %d %s" % (type(frame), start_idx, index, buffer))
                    '''
                start_idx = index + 2
                if len(frame) == 0:
                    continue
                if self._instrument is not None:
                    self._instrument.trace_raw(Instrument.TRACE_IN, frame)
                try:
                    msg = self._msg_processing(frame)
                except ValueError:
                    continue
                except NMEAInvalidFrame:
                    _logger.error("Invalid frame in %s: %s %s" % (self._transport.ref(), frame, buffer))
                    #_logger.error("Partial %s start %d last %d buffer %s" % (part, start_idx, index, buffer))
                    continue
                self._out_queue.put(msg)
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


class BufferedIPInstrument(IPInstrument):
    """
    This class provide a buffered input/output when there is a decoupling between read operation and the
    actual message read.
    This class cannot be instantiade from the Yaml
    Typical use:
    - Devices with multiple messages in a single I/O
    - N2K fast track management
    """
    def __init__(self, opts):
        super().__init__(opts)

        self._in_queue = None
        self._asynch_io = None
        self._transparent = False

    def set_message_processing(self, separator=b'\r\n', msg_processing=process_nmea0183_frame):
        if self._direction != self.WRITE_ONLY:
            self._in_queue = queue.Queue(20)
            self._asynch_io = IPAsynchReader(self, self._in_queue, separator, msg_processing)

    def open(self):
        super().open()
        if self._state == self.CONNECTED and self._asynch_io is not None:
            self._asynch_io.start()

    def read(self):
        msg = self._in_queue.get()
        self.trace(self.TRACE_IN, msg)
        return msg

    def stop(self):
        super().stop()
        if self._asynch_io is not None:
            if self._asynch_io.is_alive():
                self._asynch_io.stop()
                self._asynch_io.join()

    def set_transparency(self, flag: bool):
        if self._asynch_io is not None:
            self._asynch_io.set_transparency(flag)


class TCPBufferedReader:

    def __init__(self, connection, separator, address):
        self._connection = connection
        self._address = address
        self._ref = "%s:%d" % address
        self._in_queue = queue.Queue(10)
        self._reader = IPAsynchReader(self, self._in_queue, separator, process_nmea0183_frame)
        self._reader.start()

    def read(self):
        msg = self._in_queue.get()
        # self.trace(self.TRACE_IN, msg)
        return msg

    def stop(self):
        self._reader.stop()
        self._reader.join()
        _logger.info("TCP Buffered read stopped")

    def recv(self):
        try:
            msg = self._connection.recv(256)
        except (TimeoutError, socket.timeout):
            _logger.info("Timeout error on TCP socket")
            raise InstrumentTimeOut()
        except socket.error as e:
            _logger.error("Error receiving from TCP socket %s: %s" % (self.name(), e))
            raise InstrumentReadError()
        return msg

    def name(self):
        return "TCPBufferedReader on %s:%d" % self._address

    def ref(self):
        return self._ref


class NMEA0183TCPReader(BufferedIPInstrument):

    def __init__(self, opts):
        super().__init__(opts)
        if self._mode != self.NMEA0183:
            _logger.error("Protocol incompatible with NMEA0183 reader")
            raise ValueError
        ffilter = opts.getlist('white_list', bytes)
        self._filter = ffilter
        if ffilter is None:
            self.set_message_processing()
        else:
            _logger.info("Formatter filter %s" % self._filter)
            self.set_message_processing(msg_processing=self.filter_messages)

    def filter_messages(self, frame):
        if frame[0] == 4:
            # EOT
            return NavGenericMsg(NULL_MSG)
        msg = process_nmea0183_frame(frame)
        if msg.formatter() in self._filter:
            _logger.debug("Message retained: %s" % frame)
            return msg
        # _logger.debug("Rejected message %s" % frame)
        raise ValueError
