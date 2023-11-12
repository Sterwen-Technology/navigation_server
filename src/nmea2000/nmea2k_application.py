# -------------------------------------------------------------------------------
# Name:        NMEA2K-CAN Application class
# Purpose:     Implements the application level of the CAN layer (equivalent to J1939 CA)
#               That is a local "device". This is the default implementation with just the network management
#               No data messages processing
#
# Author:      Laurent Carré
#
# Created:     16/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import threading

from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea2000.nmea2k_device import NMEA2000Device
from nmea2000.nmea2k_name import NMEA2000Name
from nmea2000.nmea2k_iso_messages import AddressClaim, ISORequest, ProductInformation
from utilities.network_utils import get_id_from_mac

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000ApplicationPool:

    def __init__(self, controller, opts):
        self._controller = controller
        mac_source = opts.get('mac_source', str, 'eth0')
        self._mfg_code = opts.get('manufacturer_id', int, 999)
        unique_id_root = get_id_from_mac(mac_source)
        self._max_application = opts.get('max_applications', int, 8)
        self._unique_id_root = unique_id_root << (self._max_application - 1).bit_length()
        address_pool_start = opts.get('first_address', int, 128)
        self._address_pool = [a for a in range(address_pool_start, address_pool_start + (2 * self._max_application) + 1)]
        self._ap_index = 0
        self._application_count = 0

    def application_ids(self):
        address = self.get_new_address()
        if address == 254:
            raise IndexError
        if self._application_count < self._max_application:
            # create the ISO NAME
            iso_name = NMEA2000Name.create_name(
                identity_number=self._unique_id_root | self._application_count,
                manufacturer_code=self._mfg_code,
                device_class=70,
                industry_group=4,
                arbitrary_address_capable=1
                )
            self._application_count += 1
        else:
            _logger.error("NMEA2000 Applications number reached")
            raise IndexError
        return address, iso_name

    def get_new_address(self):
        while self._ap_index < len(self._address_pool):
            address = self._address_pool[self._ap_index]
            self._ap_index += 1
            if address not in self._controller.network_addresses():
                return address
        _logger.error("NMEA2000 Application address pool exhausted")
        return 254


class NMEA2000Application(NMEA2000Device):

    (WAIT_FOR_BUS, ADDRESS_CLAIM, ACTIVE) = range(10, 13)

    def __init__(self, controller):

        self._controller = controller
        # get address and create ISO Name
        self._address, self._iso_name = controller.app_pool.application_ids()
        _logger.info("Application name=%08X address=%d" % (self._iso_name.name_value, self._address))
        self._claim_timer = None
        super().__init__(self._address, name=self._iso_name)

        self._state = self.WAIT_FOR_BUS
        self._process_vector[60928] = self.address_claim_receipt
        self._controller.add_subscriber(59904, self.iso_request)
        self._product_information = ProductInformation()
        self._product_information.set_field('NMEA 2000 Version', 2100)
        self._product_information.set_field('Product Code', 150)
        self._product_information.set_product_information('NMEA MESSAGE ROUTER', 'Version 1.4',
                                                          'ROUTER Sterwen Technology', '00001')
        self._product_information.set_field('Certification Level', 0)
        self._product_information.set_field('Load Equivalency', 1)

    def send_address_claim(self):
        self.respond_address_claim()
        self._state = self.ADDRESS_CLAIM
        self._claim_timer = threading.Timer(5.0, self.address_claim_delay)
        self._claim_timer.start()

    def respond_address_claim(self):
        claim_msg = AddressClaim(self._address, name=self._iso_name)
        _logger.debug("Application address %d sending address claim" % self._address)
        self._controller.CAN_interface.send(claim_msg.message())

    def address_claim_delay(self):
        # we consider that we are good to go
        _logger.debug("Address claim for %d delay exhausted" % self._address)
        self._state = self.ACTIVE
        self._controller.CAN_interface.allow_send()
        request = ISORequest(self._address)
        self._controller.CAN_interface.send(request.message())
        t = threading.Timer(1.0, self.send_product_information)
        t.start()

    def wait_for_bus_ready(self):
        _logger.debug("Waiting for CAN Bus to be ready")
        self._controller.CAN_interface.wait_for_bus_ready()
        _logger.debug("CAN bus ready")
        self.send_address_claim()

    def start_application(self):
        _logger.debug("NMEA2000 Application device address %d starts" % self._address)
        t = threading.Thread(target=self.wait_for_bus_ready, daemon=True)
        t.start()

    def address_claim_receipt(self, address_claim_obj):
        '''
        If we are here we have a address conflict
        By the book, we need to look at the name value
        '''
        _logger.debug("Application [%d] receive address claim from address %d" % (self._address, address_claim_obj.sa))
        if self._claim_timer is not None:
            self._claim_timer.cancel()
        iso_name = address_claim_obj.name
        _logger.warning("Address claim with conflict on address %d received with name %8X. Our name: %8X" % (
                        self._address, iso_name.name_value, self._iso_name.name_value))
        if iso_name.name_value > self._iso_name.name_value:
            # here we need to change the address => not implemented
            _logger.warning("CAN address %d not available need to change it" % self._address)
            # let's find a new address
            address = self._controller.app_pool.get_new_address()
            if address == 254:
                _logger.critical("Cannot obtain a CAN address => Going off line")
                msg = AddressClaim(address, name=self._iso_name)
                _logger.warning("Application address %d sending cannot claim address" % self._address)
                self._controller.CAN_interface.send(msg.message())
                self._controller.stop()
                return
            # now we need to swap addresses
            _logger.info("Reassigning new address %d" % address)
            old_address = self._address
            self._address = address
            self._controller.change_application_address(self, old_address)
            # we go ahead for a new address claim
            self.send_address_claim()

    def iso_request(self, msg):
        if msg.da == self._address or msg.da == 255:
            _logger.debug("Application ISO request received from %d" % msg.sa)
            request = ISORequest().from_message(msg)
            if request.request_pgn == 60928:
                self.respond_address_claim()
                # self.send_product_information()
            elif request.request_pgn == 126996:
                # ok we send back the ProductInformation
                self.send_product_information()
            else:
                _logger.error("ISO Request on PGN %d not supported" % request.request_pgn)

    def send_product_information(self):
        self._product_information.sa = self._address
        _logger.debug("Send product information %s" % self._product_information.message().format1())
        self._controller.CAN_interface.send(self._product_information.message())

    def receive_data_msg(self, msg: NMEA2000Msg):
        pass








