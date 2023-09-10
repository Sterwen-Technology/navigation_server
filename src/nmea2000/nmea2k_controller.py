# -------------------------------------------------------------------------------
# Name:        NMEA2K-controller
# Purpose:     Analyse and process NMEA2000 network control messages
#
# Author:      Laurent Carré
#
# Created:     21/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import threading
import queue
import time

from nmea_routing.server_common import NavigationServer
from nmea_routing.nmea2000_msg import NMEA2000Msg
from nmea_routing.nmea2000_publisher import PgnRecord
from nmea2000.nmea2k_pgndefs import N2KUnknownPGN, N2KDecodeException
from nmea2000.nmea2k_manufacturers import Manufacturers
from nmea_routing.configuration import NavigationConfiguration

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000Device:
    '''
    This class holds the view of the devices on the NMEA2000 Network
    '''

    def __init__(self, address, properties=None):
        self._address = address
        _logger.info("NMEA Controller new device detected at address %d" % address)
        self._lastmsg_ts = 0
        self._pgn_received = {}
        self._process_vector = {60928: self.p60928,
                                126996: self.p126996
                                }
        # self._fields_60928 = None
        self._fields_126996 = None
        self._iso_name = None
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
            pgn_data = pgn_def.pgn_def.decode_pgn_data(msg.payload)
        except N2KDecodeException as e:
            _logger.error("NMEA2000 Device - PGN %d decode error %s" % (msg.pgn, e))
            return
        process_function(pgn_data)

    def set_property(self, source, property_name):
        try:
            p = source[property_name]
        except KeyError:
            _logger.error("Device address %d missing property %s" % (self._address, property_name))
            return
        self._properties[property_name] = p

    def property(self, name):
        return self._properties[name]

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

    def p60928(self, msg_data):

        #   _logger.debug("PGN 60928 data= %s" % msg_data)
        if self._iso_name is None:
            self._changed = True
            self._iso_name = msg_data['fields']["System ISO Name"]
            _logger.info("Processing ISO address claim for address %d name=%16X" %
                         (self._address, self._iso_name.name_value))
            mfg_code = self._iso_name.manufacturer_code
            _logger.debug("Device address %d claim ISO name details" % self._address)
            _logger.debug(str(self._iso_name))
            self._properties['System ISO Name'] = self._iso_name.name_value
            self._properties['Manufacturer Code'] = mfg_code
            try:
                self._properties['Manufacturer Name'] = Manufacturers.get_from_code(mfg_code).name
            except KeyError:
                self._properties['Manufacturer Name'] = "Manufacturer#%d" % mfg_code

    def p126996(self, msg_data):

        if self._fields_126996 is None:
            self._changed = True
            _logger.info("Processing Product information for address %d: %s" % (self._address, msg_data['fields']))
            self._fields_126996 = msg_data['fields']
            self.set_property(self._fields_126996, 'NMEA 2000 Version')
            self.set_property(self._fields_126996, 'Product Code')
            self.set_property(self._fields_126996, 'Certification Level')
            self.set_property(self._fields_126996, 'Load Equivalency')
            try:
                pi = self._fields_126996['Product information']
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


class NMEA2KController(NavigationServer, threading.Thread):

    def __init__(self, opts):
        super().__init__(opts)
        threading.Thread.__init__(self, name=self._name)
        self._devices = {}
        queue_size = opts.get('queue_size', int, 20)
        self._save_file = opts.get('save_file', str, None)
        if self._save_file is not None:
            self.init_save()
        self._input_queue = queue.Queue(queue_size)
        self._stop_flag = False
        NavigationConfiguration.get_conf().set_global('N2KController', self)

    def server_type(self):
        return 'NMEA2000_CONTROLLER'

    def running(self) -> bool:
        return self.is_alive()

    def send_message(self, msg: NMEA2000Msg):
        if not self.is_alive():
            # the thread is not running=> warning and discard
            _logger.error("NMEA Controller thread not running")
            return
        try:
            self._input_queue.put(msg, block=False)
        except queue.Full:
            _logger.warning("NMEA2000 Controller input queue full")

    def run(self) -> None:
        _logger.info("%s NMEA2000 Controller starts" % self._name)
        while not self._stop_flag:
            try:
                msg = self._input_queue.get(block=True, timeout=1.0)
            except queue.Empty:
                continue
            _logger.debug("NMEA Controller input %s" % msg.format1())
            # further processing here
            try:
                self.process_msg(msg)
            except Exception as e:
                _logger.error("%s NMEA2000 Controller processing error:%s on message %s" % (self._name, e, msg.format1()))

        _logger.info("%s NMEA2000 Controller stops" % self._name)

    def stop(self):
        self._stop_flag = True

    def check_device(self, address: int) -> NMEA2000Device:
        try:
            return self._devices[address]
        except KeyError:
            dev = NMEA2000Device(address)
            self._devices[address] = dev
            return dev

    def process_msg(self, msg: NMEA2000Msg):
        if msg.sa >= 254:
            return
        device = self.check_device(msg.sa)
        device.receive_msg(msg)

    def store_devices(self):
        filename = self._options.get('store', str, None)
        if filename is None:
            return

    def get_device(self) -> NMEA2000Device:
        sorted_dict = sorted(self._devices.items())
        for addr, device in sorted_dict:
            yield device

    def sort_devices(self):
        return sorted(self._devices.items())

    def get_device_by_address(self, address: int):
        try:
            return self._devices[address]
        except KeyError:
            _logger.warning('N2K No device with address:%d' % address)
        raise

    def get_device_with_property_value(self, d_property, value):
        # we use brute search
        for dev in self._devices:
            try:
                if dev.property[d_property] == value:
                    return dev
            except KeyError:
                continue
        raise KeyError

    def init_save(self):
        pass

