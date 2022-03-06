#-------------------------------------------------------------------------------
# Name:        IP Instrument
# Purpose:     Abstract class for all instruments with a IP transport interface
#
# Author:      Laurent Carré
#
# Created:     27/02/2022
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021-2022
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import socket
import logging

# from server_common import NavTCPServer
# from publisher import Publisher
from instrument import Instrument, InstrumentReadError, InstrumentTimeOut

_logger = logging.getLogger("ShipDataServer")


#################################################################
#
#   Classes for ShipModule interface
#################################################################


class IPInstrument(Instrument):

    def __init__(self, opts):
        super().__init__(opts)
        self._address = opts['address']
        self._port = opts['port']
        self._protocol = opts.get('protocol', 'TCP')
        if self._protocol == 'TCP':
            self._transport = TCP_reader(self._address, self._port)
        elif self._protocol == 'UDP':
            self._transport = UDP_reader(self._address, self._port)

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
        return self._transport.send(msg)

    def close(self):
        self._transport.close()
        self._state = self.NOT_READY


class IP_transport():

    def __init__(self, address, port):
        self._address = address
        self._port = port
        self._socket = None

    def close(self):
        self._socket.close()


class UDP_reader(IP_transport):

    def __init__(self, address, port):
        super().__init__(address, port)

    def open(self):
        _logger.info("opening UDP port %d" % self._port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self._socket.bind(('', self._port))
        except OSError as e:
            _logger.error("Error opening UDP socket:%s" % str(e))
            self._socket.close()
            return False
        self._socket.settimeout(5.0)

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
        except OSError as e:
            _logger.critical("Error writing on UDP socket: %s" % str(e))
            self.close()


class TCP_reader(IP_transport):

    def __init__(self, address, port):
        super().__init__(address, port)

    def open(self):
        _logger.info("Connecting (TCP) to NMEA source %s:%d" % (self._address, self._port))
        try:
            self._socket = socket.create_connection((self._address, self._port), 5.0)

            _logger.info("Successful TCP connection")
            return True
        except OSError as e:
            _logger.error("Connection error using TCP: %s" % str(e))

            return False

    def read(self):
        try:
            msg = self._socket.recv(256)
        except TimeoutError:
            _logger.info("Timeout error on TCP socket (%s:%d)" % (self._address, self._port))
            raise InstrumentTimeOut()
        except OSError as e:
            _logger.error("Error receiving from TCP socket: %s" % str(e))
            raise InstrumentReadError()
        return msg

    def send(self, msg):
        try:
            self._socket.sendall(msg)
        except OSError as e:
            _logger.critical("Error writing to TCP socket: %s" % str(e))
            raise








