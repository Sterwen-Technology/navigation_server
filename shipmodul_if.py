#-------------------------------------------------------------------------------
# Name:        ShipModul_if
# Purpose:     ShipModule interface
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import socket
import threading
import logging
import time

from server_common import NavTCPServer
from publisher import Publisher
from instrument import Instrument, InstrumentReadError, InstrumentTimeOut

_logger = logging.getLogger("ShipDataServer")


#################################################################
#
#   Classes for ShipModule interface
#################################################################


class ShipModulInterface(Instrument):

    @staticmethod
    def create_instrument(opts):
        # create NMEA reader on Shipmodul multiplexer
        protocol = opts.get('transport', 'UDP')

        if protocol == "UDP":
            reader = UDP_reader(opts)
        else:
            reader = TCP_reader(opts)
        return reader

    def __init__(self, opts):
        super().__init__(opts)
        self._address = opts['address']
        self._port = opts['port']
        self._socket = None

    def close(self):
        self._socket.close()
        self._state = self.NOT_READY

    def deregister(self, pub):
        if pub == self._configpub:
            self._configmode = False
            self._configpub = None
            _logger.info("Switching to normal mode for Shipmodul")

        super().deregister(pub)

    def publish(self, msg):
        if self._configmode:
            self._configpub.publish(msg)
        else:
            super().publish(msg)

    def configModeOn(self, pub):
        if len(self._address) < 4:
            _logger.error("Missing target IP address for config mode")
            return False
        else:
            self._configmode = True
            self._configpub = pub
            _logger.info("Switching to configuration mode for Shipmodul")
            return True

    def default_sender(self):
        return True


class UDP_reader(ShipModulInterface):
    def __init__(self, opts):
        super().__init__(opts)

    def open(self):
        _logger.info("opening UDP port %d" % self._port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self._socket.bind(('', self._port))
        except OSError as e:
            _logger.error("Error connecting Shipmodul via UDP:%s" % str(e))
            self._socket.close()
            return False
        self._socket.settimeout(5.0)
        self._state = self.OPEN
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
            _logger.critical("Error writing on Shipmodul: %s" % str(e))
            self.close()


class TCP_reader(ShipModulInterface):

    def __init__(self, opts):
        super().__init__(opts)

    def open(self):
        _logger.info("Connecting (TCP) to NMEA source %s:%d" % (self._address, self._port))
        try:
            self._socket = socket.create_connection((self._address, self._port), 5.0)
            self._state = self.CONNECTED
            _logger.info("Successful TCP connection")
            return True
        except OSError as e:
            _logger.error("Connection error with shipmodul using TCP: %s" % str(e))
            self._state = self.NOT_READY
            return False

    def read(self):
        try:
            msg = self._socket.recv(256)
        except TimeoutError:
            _logger.info("Timeout error on %s" % self._name)
            raise InstrumentTimeOut()
        except OSError as e:
            _logger.error("Error receiving from Shipmodul: %s" % str(e))
            raise InstrumentReadError()
        return msg

    def send(self, msg):
        try:
            self._socket.sendall(msg)
        except OSError as e:
            _logger.critical("Error writing to  Shipmodul: %s" % str(e))
            raise


class ConfigPublisher(Publisher):
    '''
    This class is used for Configuration mode, meaning when the Multiplexer utility is connected
    It gains exclusive access
    '''
    def __init__(self, connection, reader, server, address):
        super().__init__(None, internal=True, instruments=[reader], name="Shipmodul config publisher")
        self._socket = connection
        self._address = address
        self._server = server

    def process_msg(self,msg):
        try:
            self._socket.sendall(msg)
        except OSError as e:
            _logger.debug("Error writing response on config:%s" % str(e))
            return False
        return True

    def last_action(self):
        # print("Deregister config publisher")
        self._instruments[0].deregister(self)


class ShipModulConfig(NavTCPServer):

    def __init__(self, opts):
        super().__init__(opts)

        self._reader = None
        self._pub = None
        self._connection = None

    def run(self):
        try:
            self._reader = self.resolve_ref('instrument')
        except KeyError:
            _logger.error("%s no instrument associated => stop" % self.name())
            return

        _logger.info("Configuration server ready")
        while not self._stop_flag:
            _logger.info("Configuration server waiting for new connection")
            self._socket.listen(1)
            try:
                self._connection, address = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            _logger.info("New configuration connection from %s:%d" % address)
            pub = ConfigPublisher(self._connection, self._reader, self, address)
            if not self._reader.configModeOn(pub):
                self._connection.close()
                continue
            self._pub = pub
            pub.start()
            _logger.info("Shipmodul configuration active")
            while pub.is_alive():
                try:
                    msg = self._connection.recv(256)
                    if len(msg) == 0:
                        break
                except OSError as e:
                    _logger.info("config socket read error: %s" % str(e))
                    break
                _logger.debug(msg.decode().strip('\r\n'))
                try:
                    self._reader.send(msg)
                except OSError:
                    break
            _logger.info("Connection with configuration application lost")
            self._pub.stop()
            self._connection.close()
        _logger.info("Configuration server thread stops")
        self._socket.close()

    def stop(self):
        self._stop_flag = True
        if self._connection is not None:
            self._connection.close()







