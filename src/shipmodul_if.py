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
        super().__init__(opts)
        if opts.get('nmea2000', bool, False):
            self.set_message_processing()
        else:
            self.set_message_processing()

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

    @staticmethod
    def shipmodul_extract_nmea2000(frame):
        m0183 = process_nmea0183_frame(frame)
        if m0183.formatter() == b'PGN':
            fields = m0183.fields()
            pgn = int(fields[0], 16)
            prio = int(fields[1][0], 16) & 7
            dlc = int(fields[1][1], 16)
            addr = int(fields[1][2:4], 16)
            data = bytearray(dlc)
            r_data = fields[2].fromhex
            r_ind = dlc - 1
            pr_byte = 0
            while pr_byte < dlc:
                data[r_ind] = int()




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
        _logger.debug("Shipmodul publisher sending:%s" % msg)
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
            # reader = TCPBufferedReader(self._connection, b'\r\n', address)
            self._reader.set_transparency(True)
            while pub.is_alive():

                msg = self._connection.recv(256)
                if len(msg) == 0:
                    _logger.error("Shipmodul config instrument null message received")
                    break
                _logger.debug("Shipmodul conf msg %s" % msg)
                int_msg = NavGenericMsg(TRANSPARENT_MSG, raw=msg)
                if not self._reader.send(int_msg):
                    _logger.error("Shipmodul config instrument write error")
                    break

            _logger.info("Connection with configuration application lost running %s" % pub.is_alive())
            self._reader.set_transparency(False)
            self._pub.stop()
            self._connection.close()
        _logger.info("Configuration server thread stops")
        self._socket.close()

    def stop(self):
        self._stop_flag = True
        if self._connection is not None:
            self._connection.close()







