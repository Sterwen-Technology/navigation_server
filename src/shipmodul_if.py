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
from nmea0183 import process_nmea0183_frame, NMEA0183Msg
from nmea2000_msg import FastPacketHandler, NMEA2000Msg, FastPacketException
from nmea2k_pgndefs import PGNDefinitions

_logger = logging.getLogger("ShipDataServer")


#################################################################
#
#   Classes for ShipModule interface
#################################################################


class ShipModulInterface(BufferedIPInstrument):

    msg_check = NavGenericMsg(TRANSPARENT_MSG, b'$PSMDVER\r\n')
    version_fmt = b'$PSMDVER'
    version_fmt_l = len(version_fmt)

    def __init__(self, opts):
        super().__init__(opts)
        self._separator = b'\r\n'
        self._separator_len = 2
        if opts.get('nmea2000', bool, False):
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
            fields = m0183.fields()
            pgn = int(fields[0], 16)
            attribute = int(fields[1], 16)
            prio = attribute >> 12 & 7
            dlc = attribute >> 8 & 0xF
            addr = attribute & 0xFF
            data = bytearray(dlc)
            pr_byte = 0
            l_hex = len(fields[2])
            i_hex = l_hex - 2
            while pr_byte < dlc:
                data[pr_byte] = int(fields[2][i_hex:i_hex+2], 16)
                pr_byte += 1
                i_hex -= 2
            # now the PGN sentence is decoded
            if self._fast_packet_handler.is_pgn_active(pgn, data):
                try:
                    data = self._fast_packet_handler.process_frame(pgn, data)
                except FastPacketException:
                    _logger.error("Shipmodul Fast packet error frame: %s pgn %d data %s" % (frame, pgn, data.hex()))
                    raise ValueError
                if data is None:
                    raise ValueError  # no error but just to escape
            elif PGNDefinitions.pgn_definition(pgn).fast_packet():
                try:
                    self._fast_packet_handler.process_frame(pgn, data)
                except FastPacketException:
                    _logger.error("Shipmodul Fast packet error on initial frame %s data %s" % (frame, data.hex()))
                raise ValueError  # no error but just to escape
            msg = NMEA2000Msg(pgn, prio, addr, 0, data)
            _logger.debug("Shipmodul PGN decode:%s" % str(msg))
            gmsg = NavGenericMsg(N2K_MSG, raw=frame, msg=msg)
            return gmsg
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
        else:
            self._check_in_progress = True
            self._check_ok = False
            self.send(self.msg_check)




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
        _logger.debug("Shipmodul publisher sending:%s" % msg.raw)
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







