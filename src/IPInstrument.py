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

# from server_common import NavTCPServer
# from publisher import Publisher
import threading

from instrument import Instrument, InstrumentReadError, InstrumentTimeOut

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

        self._protocol = opts.get('transport', str, 'TCP')
        if self._protocol == 'TCP':
            self._transport = TCP_reader(self._address, self._port, self._timeout)
        elif self._protocol == 'UDP':
            self._transport = UDP_reader(self._address, self._port, self._timeout)

    def open(self):

        if self._transport.open():
            self._state = self.OPEN
            if self._protocol == 'TCP':
                self._state = self.CONNECTED
        else:
            self._state = self.NOT_READY

    def read(self):
        return self._transport.read()

    def send(self, msg):
        if self._state == self.NOT_READY:
            _logger.error("Write attempt on non ready transport: %s" % self.name())
            return False
        return self._transport.send(msg)

    def close(self):
        self._transport.close()
        self._state = self.NOT_READY


class IP_transport():

    def __init__(self, address, port, timeout):
        self._address = address
        self._port = port
        self._ref = "%s:%d" % (self._address, self._port)
        self._socket = None
        self._timeout = timeout

    def close(self):
        if self._socket is not None:
            self._socket.close()


class UDP_reader(IP_transport):

    def __init__(self, address, port, timeout):
        super().__init__(address, port, timeout)

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

    def read(self):
        try:
            data, address = self._socket.recvfrom(256)
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

    def __init__(self, address, port, timeout):
        super().__init__(address, port, timeout)

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

    def read(self):
        try:
            msg = self._socket.recv(256)
        except (TimeoutError, socket.timeout) :
            _logger.info("Timeout error on TCP socket %s" % self._ref)
            raise InstrumentTimeOut()
        except socket.error as e:
            _logger.error("Error receiving from TCP socket %s: %s" % (self._ref, str(e)))
            raise InstrumentReadError()
        return msg

    def send(self, msg):
        try:
            self._socket.sendall(msg)
            return True
        except OSError as e:
            _logger.critical("Error writing to TCP socket %s: %s" % (self._ref, str(e)))
            return False


class IPAsynchReader(threading.Thread):

    def __init__(self, transport, out_queue, separator, msg_processing):
        super().__init__()
        self._transport = transport
        self._out_queue = out_queue
        self._separator = separator
        self._msg_processing = msg_processing
        self._stop_flag = False
        self._buffer = bytearray(512)

    def run(self):
        part = False
        part_buf = bytearray()
        while not self._stop_flag:
            try:
                buffer = self._transport.read()
            except InstrumentTimeOut:
                continue
            except InstrumentReadError:
                break
            start_idx = 0
            end_idx = len(buffer)
            while True:
                if start_idx >= end_idx:
                    break
                index = buffer.find(self._separator, start_idx, end_idx)
                if index == -1:
                    if part:
                        _logger.error("YDFrame missing delimiter start %d end %d" % (start_idx, end_idx))
                        _logger.error("YDFrame missing delimiter %s" % buffer[start_idx: end_idx].hex(' ', 2))
                    else:
                        part = True
                        part_buf = buffer[start_idx: end_idx]
                        _logger.debug("Partial frame (%d %d): %s" % (start_idx, end_idx, part_buf))
                    break
                if part:
                    frame = part_buf + buffer[start_idx:index]
                    _logger.debug("Frame reconstruction %s %s" % (part_buf, buffer[start_idx:index]))
                    part = False
                else:
                    frame = buffer[start_idx:index]
                start_idx = index + 2
                try:
                    msg = self._msg_processing(frame)
                except ValueError:
                    continue
                self._out_queue.put(msg)
                if self._stop_flag:
                    break
        _logger.info("Asynch reader stopped")

    def stop(self):
        self._stop_flag = True


class BufferedIPInstrument(IPInstrument):
    '''
    This class provide a buffered input/output when there is a decoupling between read operation and the
    actual message read.
    Typical use:
    - Devices with multiple messages in a single I/O
    - N2K fast track management
    '''
    def __init__(self, opts, seperator, msg_processing):
        super().__init__(opts)
        self._in_queue = queue.Queue(20)
        self._asynch_io = IPAsynchReader (self._transport, self._in_queue, seperator, msg_processing)

    def open(self):
        super().open()
        if self._state == self.CONNECTED:
            self._asynch_io.start()

    def read(self):
        return self._in_queue.get()

    def stop(self):
        super().stop()
        self._asynch_io.stop()
        self._asynch_io.join()




