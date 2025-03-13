# -------------------------------------------------------------------------------
# Name:        NMEA2K-device
# Purpose:     Controller representation for devices on the bus
#
# Author:      Laurent Carré
#
# Created:     18/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import time


from navigation_server.router_core import NMEA2000Msg
from navigation_server.nmea2000_datamodel import N2KUnknownPGN
from .nmea2k_iso_messages import AddressClaim, ConfigurationInformation, ProductInformation, Heartbeat
from navigation_server.router_common import MessageServerGlobals, find_pgn


_logger = logging.getLogger("ShipDataServer." + __name__)

class PgnRecord:

    def __init__(self, pgn: int):
        self._pgn = pgn
        self._pgn_def = find_pgn(pgn)
        self._clock = time.time()
        self._count = 1

    @property
    def pgn(self):
        return self._pgn

    @property
    def pgn_def(self):
        return self._pgn_def

    def tick(self):
        self._count += 1

class NMEA2000Device:
    '''
    This class holds the view of the devices on the NMEA2000 Network (proxy devices)
    '''

    def __init__(self, address, name=None):
        '''
        Parameters
        address: device address [0, 253] on the bus
        name: 64bits ISO/J1939 NAME (Supported by NMEA2000Name class)
        '''
        self._address = address
        _logger.info("NMEA Controller new device detected at address %d" % address)
        self._lastmsg_ts = 0
        self._pgn_received = {}
        self._process_vector = {60928: self.p60928,
                                126993: self.p126993,
                                126996: self.p126996,
                                126998: self.p126998
                                }
        # self._fields_60928 = None
        self._product_information = None
        self._configuration_info = None
        self._heartbeat = None
        self._iso_name = name
        self._manufacturer_name = None
        self._changed = True
        self._product_info_sent = False

    def receive_msg(self, msg: NMEA2000Msg):
        _logger.debug("NMEA2000 Device manager: New message PGN %d for device @%d" % (msg.pgn, self._address))
        self._lastmsg_ts = time.time()
        try:
            pgn_def = self.add_pgn_count(msg.pgn)
        except N2KUnknownPGN:
            return
        try:
            self._process_vector[msg.pgn](msg)
        except KeyError:
            _logger.debug("Device address %d => no process function for PGN %d" % (self._address, msg.pgn))
            return

    def is_proxy(self):
        return True

    @property
    def address(self):
        return self._address

    @property
    def iso_name(self):
        return self._iso_name

    @property
    def configuration_information(self) -> ConfigurationInformation:
        return self._configuration_info

    @property
    def manufacturer_name(self) -> str:
        return self._manufacturer_name

    @property
    def product_information_sent(self) -> bool:
        return self._product_info_sent

    @product_information_sent.setter
    def product_information_sent(self, flag:bool):
        self._product_info_sent = flag

    def add_pgn_count(self, pgn) -> PgnRecord:
        try:
            pgn_def = self._pgn_received[pgn]
            pgn_def.tick()
        except KeyError:
            pgn_def = PgnRecord(pgn)
            self._pgn_received[pgn] = pgn_def
        return pgn_def

    def p60928(self, msg: NMEA2000Msg):

        #   _logger.debug("PGN 60928 data= %s" % msg_data)
        n2k_obj = AddressClaim()
        n2k_obj.from_message(msg)
        if self._iso_name is None or self._iso_name != n2k_obj.name:
            self._changed = True
            self._iso_name = n2k_obj.name
            _logger.debug("Processing ISO address claim for address %d name=%16X" %
                         (self._address, self._iso_name.name_value))
            mfg_code = self._iso_name.manufacturer_code
            _logger.debug("Device address %d claim ISO name details" % self._address)
            _logger.debug(str(self._iso_name))
            try:
                self._manufacturer_name = MessageServerGlobals.manufacturers.by_code(mfg_code).name
            except KeyError:
                self._manufacturer_name = "Manufacturer#%d" % mfg_code

    def p126993(self, msg: NMEA2000Msg):
        self._heartbeat = Heartbeat(message=msg)
        _logger.debug("Device %d heartbeat received: %s" % (msg.sa, self._heartbeat))

    def p126996(self, msg: NMEA2000Msg):

        if self._product_information is None:
            self._changed = True
            n2k_obj = ProductInformation(message=msg)
            _logger.debug("Processing Product information for address %d: %s" % (self._address, n2k_obj))
            self._product_information = n2k_obj
            # print(product_name,"|", product_version,"|", description, "|", firmware)

    def p126998(self, msg: NMEA2000Msg):
        self._configuration_info = ConfigurationInformation(message=msg)
        _logger.debug("Received Configuration info for address %d: %s" % (self._address, self._configuration_info))

    #navigation_definitions asDict(self):
        # return {'address:': self._address, 'properties': self._properties}

    def changed(self) -> bool:
        return self._changed

    def clear_change_flag(self):
        self._changed = False

    @property
    def product_information(self) -> ProductInformation:
        return self._product_information

    @property
    def last_time_seen(self):
        return self._lastmsg_ts

