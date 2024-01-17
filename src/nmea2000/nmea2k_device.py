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


from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea2000.nmea2k_publisher import PgnRecord
from nmea2000.nmea2k_pgndefs import N2KUnknownPGN, N2KDecodeException
from nmea2000.nmea2k_iso_messages import AddressClaim, ConfigurationInformation, ProductInformation, Heartbeat
from nmea2000.nmea2k_manufacturers import Manufacturers
from nmea2000.nmea2k_factory import NMEA2000Factory
from utilities.global_variables import MessageServerGlobals


_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000Device:
    '''
    This class holds the view of the devices on the NMEA2000 Network
    '''

    def __init__(self, address, properties=None, name=None):
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
        self._changed = True
        if properties is None:
            self._properties = {}
        else:
            self._properties = properties

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

    def set_property(self, source, property_name):
        try:
            p = source[property_name]
        except KeyError:
            _logger.error("Device address %d missing property %s" % (self._address, property_name))
            return
        self._properties[property_name] = p

    def property_value(self, name):
        return self._properties[name]

    @property
    def address(self):
        return self._address

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
        if self._iso_name is None:
            self._changed = True
            n2k_obj = AddressClaim()
            n2k_obj.from_message(msg)
            self._iso_name = n2k_obj.name
            _logger.info("Processing ISO address claim for address %d name=%16X" %
                         (self._address, self._iso_name.name_value))
            mfg_code = self._iso_name.manufacturer_code
            _logger.debug("Device address %d claim ISO name details" % self._address)
            _logger.debug(str(self._iso_name))
            self._properties['System ISO Name'] = self._iso_name.name_value
            self._properties['Manufacturer Code'] = mfg_code
            try:
                self._properties['Manufacturer Name'] = MessageServerGlobals.manufacturers.by_code(mfg_code).name
            except KeyError:
                self._properties['Manufacturer Name'] = "Manufacturer#%d" % mfg_code

    def p126993(self, msg: NMEA2000Msg):
        self._heartbeat = Heartbeat(message=msg)
        _logger.info("Device %d heartbeat received: %s" % (msg.sa, self._heartbeat))

    def p126996(self, msg: NMEA2000Msg):

        if self._product_information is None:
            self._changed = True
            n2k_obj = ProductInformation(message=msg)
            _logger.info("Processing Product information for address %d: %s" % (self._address, n2k_obj))
            self._product_information = n2k_obj
            self._properties['NMEA 2000 Version'] = n2k_obj.nmea2000_version
            self._properties['Product Code'] = n2k_obj.product_code
            self._properties['Certification Level'] = n2k_obj.certification_level
            self._properties['Load Equivalency'] = n2k_obj.load_equivalency
            self._properties['Product name'] = n2k_obj.model_id

            self._properties['Product version'] = n2k_obj.model_version
            self._properties['Description'] = n2k_obj.model_serial_code
            self._properties['Firmware'] = n2k_obj.software_version
            # print(product_name,"|", product_version,"|", description, "|", firmware)

    def p126998(self, msg: NMEA2000Msg):
        self._configuration_info = ConfigurationInformation(message=msg)
        _logger.info("Configuration info for address %d: %s" % (self._address, self._configuration_info))

    def asDict(self):
        return {'address:': self._address, 'properties': self._properties}

    def changed(self) -> bool:
        return self._changed

    def clear_change_flag(self):
        self._changed = False

    @property
    def product_information(self) -> ProductInformation:
        return self._product_information

