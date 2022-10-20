#-------------------------------------------------------------------------------
# Name:        ShipModul_if
# Purpose:     ShipModule interface
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License V2.0
#-------------------------------------------------------------------------------

import socket
import logging

from nmea_routing.server_common import NavTCPServer, ConnectionRecord
from nmea_routing.publisher import Publisher
from nmea_routing.IPCoupler import BufferedIPCoupler
from nmea_routing.generic_msg import *
from nmea_routing.nmea0183 import NMEA0183Msg, NMEA0183Sentences
from nmea_routing.nmea2000_msg import FastPacketHandler, NMEA2000Msg, FastPacketException
from nmea2000.nmea2k_pgndefs import PGNDefinitions, N2KUnknownPGN

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


#################################################################
#
#   Classes for ShipModule Miniplex3 interface over IP
#
#################################################################


class ShipModulInterface(BufferedIPCoupler):

    msg_check = NavGenericMsg(TRANSPARENT_MSG, b'$PSMDVER\r\n')
    version_fmt = b'$PSMDVER'
    version_fmt_l = len(version_fmt)

    def __init__(self, opts):
        super().__init__(opts)
        self._separator = b'\r\n'
        self._separator_len = 2
        if self._mode in (self.NMEA2000, self.NMEA_MIX):
            self._fast_packet_handler = FastPacketHandler(self)
            self.set_message_processing(msg_processing=self.shipmodul_extract_nmea2000)
        else:
            self.set_message_processing(msg_processing=self.shipmodul_process_frame)
        self._check_ok = False

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
            self._check_in_progress = False  # In any case no check during configuration session
            _logger.info("Switching to configuration mode for Shipmodul")
            return True

    def default_sender(self):
        return True

    def shipmodul_extract_nmea2000(self, frame):
        if frame[0] == 4:
            # EOT
            return NavGenericMsg(NULL_MSG)
        m0183 = self.shipmodul_process_frame(frame)
        if m0183.formatter() == b'PGN':
            return self.mxpgn_decode(m0183)
        else:
            return m0183

    def shipmodul_process_frame(self, frame):
        '''
        Extract tag header when present
        :param frame:
        :return: NMEA0183Msg
        '''
        if frame[0] == 4:
            # EOT
            return NavGenericMsg(NULL_MSG)

        if self._check_in_progress:
            if frame[:self.version_fmt_l] == self.version_fmt:
                _logger.info("Check connection answer: %s" % frame)
                self._check_ok = True
                return NMEA0183Msg(frame)

        if frame[:2] == b'\\s':
            end_of_tag = frame[2:].index(b'\\')
            msg = NMEA0183Msg(frame[end_of_tag+1:])
        else:
            msg = NMEA0183Msg(frame)
        return msg

    def check_connection(self):
        '''
        Send a version message to check the connectivity when no activity
        :return:
        '''
        if self._check_in_progress:
            if not self._check_ok:
                _logger.error("Shipmodul no answer on version request")
                self.close()
            self._check_in_progress = False
        elif not self._configmode:
            # configuration session in progress no check
            self._check_in_progress = True
            self._check_ok = False
            self.send(self.msg_check)

    def encode_nmea2000(self, msg: NMEA2000Msg) -> NavGenericMsg:
        _logger.debug("Shipmodul sending N2K message %s" % msg)
        pgn = b'%06X' % msg.pgn
        priow = msg.prio << 12
        rdata = bytearray(8)

        def encode(data):
            l = len(data)
            id = 7
            for b in data[:l]:
                rdata[id] = b
                id -= 1
            attr = 0x8000 | priow | l << 8 | msg.da
            # print("Shipmodul encode source:", data.hex(), "result:", rdata[id+1:].hex())
            sd = b'$MXPGN,%s,%4X,%s' % (pgn, attr, rdata[id+1:].hex().encode())
            checksum = NMEA0183Sentences.b_checksum(sd[1:])
            frame = b'%s*%02X\r\n' % (sd, checksum)
            return NavGenericMsg(TRANSPARENT_MSG, raw=frame)

        if msg.fast_packet:
            for data_packet in self._fast_packet_handler.split_message(msg.pgn, msg.payload):
                yield encode(data_packet)
        else:
            yield encode(msg.payload)

    def validate_n2k_frame(self, frame):
        pass


class ConfigPublisher(Publisher):
    '''
    This class is used for Configuration mode, meaning when the Multiplexer utility is connected
    It gains exclusive access
    '''
    def __init__(self, connection, reader, server, address):
        super().__init__(None, internal=True, couplers=[reader], name="Shipmodul config publisher")
        self._socket = connection
        self._address = address
        self._server = server

    def process_msg(self, msg):
        _logger.debug("Shipmodul publisher sending:%s" % msg.raw)
        try:
            self._socket.sendall(msg.raw)
        except OSError as e:
            _logger.debug("Error writing response on config:%s" % str(e))
            return False
        return True

    def last_action(self):
        # print("Deregister config publisher")
        self._couplers[0].deregister(self)


class ShipModulConfig(NavTCPServer):

    def __init__(self, opts):
        super().__init__(opts)

        self._reader = None
        self._pub = None
        self._connection = None
        self._address = None

    def run(self):

        self.update_couplers()
        _logger.info("Configuration server ready")
        if self._reader is None:
            _logger.critical("No associated Miniplex coupler => Stop server")
            return
        while not self._stop_flag:
            _logger.debug("Configuration server waiting for new connection")
            self._socket.listen(1)
            try:
                self._connection, self._address = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            _logger.info("New configuration connection from %s:%d" % self._address)
            pub = ConfigPublisher(self._connection, self._reader, self, self._address)
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
                    _logger.error("Shipmodul config coupler null message received")
                    break
                _logger.debug("Shipmodul conf msg %s" % msg)
                int_msg = NavGenericMsg(TRANSPARENT_MSG, raw=msg)
                if not self._reader.send(int_msg):
                    _logger.error("Shipmodul config coupler write error")
                    break

            _logger.info("Connection with configuration application lost running %s" % pub.is_alive())
            self._reader.set_transparency(False)
            self._pub.stop()
            self._connection.close()
            self._connection = None
        _logger.info("Configuration server thread stops")
        self._socket.close()

    def stop(self):
        self._stop_flag = True
        if self._connection is not None:
            self._connection.close()

    def update_couplers(self):

        self._reader = self.resolve_ref('coupler')
        if self._reader is None:
            _logger.error("%s no coupler associated => stop" % self.name())

    def nb_connections(self):
        if self._connection is not None:
            return 1
        else:
            return 0

    def connections(self):
        result = []
        if self._connection is not None:
            result.append(ConnectionRecord(self._address[0], self._address[1], 0))
        return result





