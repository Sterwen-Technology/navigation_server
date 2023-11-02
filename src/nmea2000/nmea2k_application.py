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

from nmea2000.nmea2k_device import NMEA2000Device
from nmea2000.nmea2k_name import NMEA2000Name
from nmea2000.nmea2k_iso_messages import AddressClaim, ISORequest, ProductInformation

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000Application(NMEA2000Device):

    (WAIT_FOR_BUS, ADDRESS_CLAIM, ACTIVE) = range(10, 13)

    def __init__(self, controller, opts):

        self._controller = controller
        self._unique_id = opts.get('unique_id', int, 0)
        self._address = opts.get('address', int, 112)
        self._mfg_code = opts.get('manufacturer_id', int, 999)
        super().__init__(self._address)
        # create ISO Name
        self._iso_name = NMEA2000Name.create_name(
            identity_number=self._unique_id,
            manufacturer_code=self._mfg_code,
            device_class=70,
            industry_group=4,
            arbitrary_address_capable=1
        )
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
        claim_msg = AddressClaim(self._address, self._iso_name)
        _logger.debug("Application address %d sending address claim" % self._address)
        self._controller.CAN_interface.send(claim_msg.message())
        self._state = self.ADDRESS_CLAIM
        t = threading.Timer(5.0, self.address_claim_delay)
        t.start()

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
        self.send_address_claim()

    def start(self):
        _logger.debug("NMEA2000 Application device address %d starts" % self._address)
        t = threading.Thread(target=self.wait_for_bus_ready, daemon=True)
        t.start()

    def address_claim_receipt(self, data):
        '''
        If we are here we have a address conflict
        By the book, we need to look at the name value
        '''

        iso_name = data['fields']["System ISO Name"]
        _logger.warning("Address claim on address %d received with name %8X. Our name: %8X" % (
                        self._address, iso_name.name_value, self._iso_name.name_value))
        if iso_name > self._iso_name:
            # here we need to change the address => not implemented
            _logger.critical("CAN address %d not available please change it" % self._address)
        else:
            # we go ahead
            self.send_address_claim()

    def iso_request(self, msg):
        if msg.da == self._address or msg.da == 255:
            _logger.debug("Application ISO request received")
            request = ISORequest().from_message(msg)
            if request.request_pgn == 60928:
                self.send_address_claim()
            elif request.request_pgn == 126996:
                # ok we send back the ProductInformation
                self.send_product_information()
            else:
                _logger.error("ISO Request on PGN %d not supported" % request.request_pgn)

    def send_product_information(self):
        self._product_information.sa = self._address
        _logger.debug("Send product information %s" % self._product_information.message().format1())
        self._controller.CAN_interface.send(self._product_information.message())








