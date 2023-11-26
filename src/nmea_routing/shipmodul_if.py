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
from nmea_routing.coupler import Coupler, IncompleteMessage
from nmea_routing.IPCoupler import BufferedIPCoupler
from nmea_routing.generic_msg import *
from nmea0183.nmea0183_msg import NMEA0183Msg, NMEA0183Sentences
from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea2000.nmea2k_fast_packet import FastPacketHandler, FastPacketException
from nmea2000.nmea2k_pgndefs import N2KUnknownPGN, PGNDef

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
        self._total_msg_raw += 1
        m0183 = self.shipmodul_process_frame(frame)
        if m0183.formatter() == b'PGN':
            return self.mxpgn_decode(self, m0183)
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
        self._total_msg_raw += 1
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

    @staticmethod
    def mxpgn_decode(coupler, m0183: NMEA0183Msg) -> NavGenericMsg:
        '''
        Decode a NMEA0183 message encapsulating NMEA2000 in Shipmodul Miniplex format
        :param coupler: The actual coupler
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
        # if NMEA_MIX, return without decoding except for ISO protocol messages when N2KController is present
        if coupler.mode == Coupler.NMEA_MIX:
            if coupler.n2k_controller is None or not PGNDef.pgn_for_controller(pgn):
                # return a partially decoded NMEA2000 message
                msg = NMEA2000Msg(pgn, prio, source_addr, dest_addr)
                gmsg = NavGenericMsg(N2K_MSG, raw=m0183.raw, msg=msg)
                return gmsg
        # here we continue decoding in NMEA2000 mode and for ISO messages
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
                _logger.info("%s MXPGN decode %s SA=%d data=%s" % (coupler.name(), e, source_addr, data.hex()))
                raise IncompleteMessage
            return fp

        # self.trace_n2k_raw(pgn, source_addr, prio, data)
        _logger.debug("start processing PGN %d" % pgn)
        if coupler.fast_packet_handler.is_pgn_active(pgn, source_addr, data):
            _logger.debug("Shipmodul PGN %d on address %d fast packet active" % (pgn, source_addr))
            try:
                data = coupler.fast_packet_handler.process_frame(pgn, source_addr, data, coupler.add_event_trace)
            except FastPacketException as e:
                _logger.error("Shipmodul Fast packet error %s pgn %d data %s" % (e, pgn, data.hex()))
                coupler.add_event_trace(str(e))
                raise IncompleteMessage
            if data is None:
                raise IncompleteMessage  # no error but just to escape
        elif check_pgn():
            _logger.debug("Shipmodul PGN %d is fast packet" % pgn)
            try:
                data = coupler.fast_packet_handler.process_frame(pgn, source_addr, data, coupler.add_event_trace)
            except FastPacketException as e:
                _logger.error("Shipmodul Fast packet error %s on initial frame pgn %d data %s" % (e, pgn, data.hex()))
                coupler.add_event_trace(str(e))
            raise IncompleteMessage  # no error but just to escape
        msg = NMEA2000Msg(pgn, prio, source_addr, dest_addr, data)
        _logger.debug("Shipmodul PGN decode:%s" % str(msg))  # very intensive => to be removed
        gmsg = NavGenericMsg(N2K_MSG, msg=msg)
        return gmsg


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
        _logger.debug("ShipModulConfig server starts")
        self.check_couplers()
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

    def check_couplers(self):
        _logger.debug("ShipModulConfig check couplers")
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





