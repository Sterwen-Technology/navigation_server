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
                                126996: self.p126996
                                }
        # self._fields_60928 = None
        self._obj_126996 = None
        self._iso_name = name
        self._changed = True
        if properties is None:
            self._properties = {}
        else:
            self._properties = properties

    def receive_msg(self, msg: NMEA2000Msg):
        _logger.debug("New message PGN %d for device @%d" % (msg.pgn, self._address))
        self._lastmsg_ts = time.time()
        try:
            pgn_def = self.add_pgn_count(msg.pgn)
        except N2KUnknownPGN:
            return
        try:
            process_function = self._process_vector[msg.pgn]
        except KeyError:
            return
        try:
            n2k_obj = NMEA2000Factory.build_n2k_object(msg)
        except N2KDecodeException as e:
            _logger.error("NMEA2000 Device - PGN %d decode error %s" % (msg.pgn, e))
            return
        process_function(n2k_obj)

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

    def p60928(self, n2k_obj):

        #   _logger.debug("PGN 60928 data= %s" % msg_data)
        if self._iso_name is None:
            self._changed = True
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

    def p126996(self, n2k_obj):

        if self._obj_126996 is None:
            self._changed = True
            _logger.info("Processing Product information for address %d: %s" % (self._address, n2k_obj.fields))
            self._obj_126996 = n2k_obj
            self.set_property(self._obj_126996.fields, 'NMEA 2000 Version')
            self.set_property(self._obj_126996.fields, 'Product Code')
            self.set_property(self._obj_126996.fields, 'Certification Level')
            self.set_property(self._obj_126996.fields, 'Load Equivalency')
            try:
                pi = self._obj_126996.fields['Product information']
            except KeyError:
                _logger.error("No Product Information in PGN 126996")
                return
            lpi = len(pi)
            self._properties['Product name'] = pi[0:32].rstrip(' \x00')
            if lpi >= 64:
                self._properties['Product version'] = pi[32:64].rstrip(' \x00')
                if lpi >= 96:
                    self._properties['Description'] = pi[64:96].rstrip(' \x00')
                    if lpi >= 128:
                        self._properties['Firmware'] = pi[96:128].rstrip(' \x00')
            # print(product_name,"|", product_version,"|", description, "|", firmware)

    def asDict(self):
        return {'address:': self._address, 'properties': self._properties}

    def changed(self) -> bool:
        return self._changed

    def clear_change_flag(self):
        self._changed = False

