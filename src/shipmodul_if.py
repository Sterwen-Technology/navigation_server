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
import logging

from server_common import NavTCPServer
from publisher import Publisher
from IPInstrument import IPInstrument, BufferedIPInstrument, TCPBufferedReader
from generic_msg import *
from nmea0183 import process_nmea0183_frame

_logger = logging.getLogger("ShipDataServer")


#################################################################
#
#   Classes for ShipModule interface
#################################################################


class ShipModulInterface(BufferedIPInstrument):

    def __init__(self, opts):
        super().__init__(opts, b'\r\n', process_nmea0183_frame)

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

    def process_msg(self, msg):
        _logger.debug("Shipmodul publisher sending:%s" % msg.printable())
        try:
            self._socket.sendall(msg.raw)
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
            _logger.debug("Configuration server waiting for new connection")
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
            reader = TCPBufferedReader(self._connection, b'\r\n')
            while pub.is_alive():

                msg = reader.read()
                if msg.type == NULL_MSG:
                    _logger.error("Shipmodul config instrument null message received")
                    break
                _logger.debug(msg.printable())
                if not self._reader.send(msg):
                    _logger.error("Shipmodul config instrument write error")
                    break

            _logger.info("Connection with configuration application lost running %s" % pub.is_alive())
            self._pub.stop()
            reader.stop()
            self._connection.close()
        _logger.info("Configuration server thread stops")
        self._socket.close()

    def stop(self):
        self._stop_flag = True
        if self._connection is not None:
            self._connection.close()







