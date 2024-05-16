# -------------------------------------------------------------------------------
# Name:        NMEA2K-CAN Application class
# Purpose:     Implements the application level of the CAN layer (equivalent to J1939 CA)
#               That is a local "device". This is the default implementation with just the network management
#               No data messages processing
#
# Author:      Laurent Carré
#
# Created:     16/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import threading

from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea2000.nmea2k_device import NMEA2000Device
from nmea2000.nmea2k_name import NMEA2000MutableName
from nmea2000.nmea2k_iso_messages import (AddressClaim, ISORequest, ProductInformation, ConfigurationInformation,
                                         AcknowledgeGroupFunction, create_group_function, CommandedAddress,
                                          CommandGroupFunction, pgn_function_table)
# from nmea2000.nmea2k_active_controller import NMEA2KActiveController
from utilities.network_utils import get_id_from_mac
from utilities.global_variables import MessageServerGlobals

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
            iso_name = NMEA2000MutableName(
                identity_number=self._unique_id_root | self._application_count,
                manufacturer_code=self._mfg_code,
                device_class=25,
                device_function=130,
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
        self._application_type_name = "Generic NMEA2000 CA"
        # get address and create ISO Name
        self._address, self._iso_name = controller.app_pool.application_ids()

        _logger.info("Controller Application ECU:%s ISO Name=%08X address=%d type:%s" %
                     (controller.name, self._iso_name.name_value, self._address, self._application_type_name))
        self._claim_timer = None
        super().__init__(self._address, name=self._iso_name)

        self._app_state = self.WAIT_FOR_BUS
        # vector for addressed messages
        self._process_vector[60928] = self.address_claim_receipt
        self._process_vector[59904] = self.iso_request
        self._process_vector[126208] = self.group_function_handler
        # vector for non-addressed ones
        self._process_broadcast_vector = {
            59904: self.iso_request,
            60928: self.remote_address_claim,
            65240: self.commanded_address_request
        }
        self._product_information = ProductInformation()
        self.init_product_information()
        self._configuration_information = ConfigurationInformation()
        self.init_configuration_information()
        self._manufacturer_name = MessageServerGlobals.manufacturers.by_code(self._iso_name.manufacturer_code).name

    def init_product_information(self):
        '''
        This method is meant to be overloaded in subclasses to create specific product information
        '''
        self._product_information.nmea2000_version = 2100
        self._product_information.product_code = 1226
        self._product_information.set_product_information('NMEA MESSAGE ROUTER',
                                                          f'Version {MessageServerGlobals.version}',
                                                          'ROUTER Sterwen Technology', '00001')
        self._product_information.certification_level = 1
        self._product_information.load_equivalency = 1

    def init_configuration_information(self):
        '''
        This method is meant to be overloaded in subclasses to create specific configuration information
        '''
        self._configuration_information.installation_1 = "Test1"
        self._configuration_information.installation_2 = "Test2"
        self._configuration_information.manufacturer_info = "Sterwen Technology SAS"

    def send_address_claim(self, da=255):
        self.respond_address_claim(da)
        self._app_state = self.ADDRESS_CLAIM
        self._claim_timer = threading.Timer(0.4, self.address_claim_delay)
        self._claim_timer.start()

    def respond_address_claim(self, da):
        claim_msg = AddressClaim(self._address, name=self._iso_name, da=da)
        _logger.debug("Application address %d sending address claim to %d" % (self._address, claim_msg.da))
        self._controller.CAN_interface.send(claim_msg.message(), force_send=True)

    def address_claim_delay(self):
        # we consider that we are good to go
        _logger.debug("Address claim for %d delay exhausted" % self._address)
        self._app_state = self.ACTIVE
        self._controller.CAN_interface.allow_send()
        self.send_iso_request(255, 60928)
        # request = ISORequest(self._address)
        # self._controller.CAN_interface.send(request.message())
        # t = threading.Timer(1.0, self.send_product_information)
        # t.start()

    def wait_for_bus_ready(self):
        _logger.debug("Waiting for CAN Bus to be ready")
        self._controller.CAN_interface.wait_for_bus_ready()
        _logger.debug("CAN bus ready")
        self.send_address_claim()

    def start_application(self):
        _logger.debug("NMEA2000 Application device address %d starts" % self._address)
        t = threading.Thread(target=self.wait_for_bus_ready, daemon=True)
        t.start()

    def address_claim_receipt(self, msg: NMEA2000Msg):
        '''
        If we are here we have an address conflict
        By the book, we need to look at the name value
        '''
        _logger.debug("Application [%d] receive address claim from address %d da=%d" % (self._address, msg.sa, msg.da))
        if self._claim_timer is not None:
            self._claim_timer.cancel()
        address_claim_obj = AddressClaim(message=msg, da=msg.sa)
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
                msg = AddressClaim(address, name=self._iso_name, da=msg.sa)
                _logger.warning("Application address %d sending cannot claim address" % self._address)
                self._controller.CAN_interface.send(msg.message(), force_send=True)
                self._controller.stop()
                return
            # now we need to swap addresses
            self.change_address(address)

    def change_address(self, address):
        _logger.info("Reassigning new address %d" % address)
        old_address = self._address
        self._address = address
        self._controller.change_application_address(self, old_address)
        # we go ahead for a new address claim
        self.send_address_claim()

    def iso_request(self, msg):
        # _logger.debug("Received ISO request from %d da=%d" % (msg.sa, msg.da))
        if msg.da == self._address or msg.da == 255:
            request = ISORequest().from_message(msg)
            _logger.debug("Application ISO request received from %d for pgn %d" % (msg.sa, request.request_pgn))
            if request.request_pgn == 60928:
                self.respond_address_claim(msg.sa)
            elif request.request_pgn == 126996:
                # ok we send back the ProductInformation
                self.send_product_information()
            elif request.request_pgn == 126998:
                self.send_configuration_information()
            else:
                _logger.error("ISO Request on PGN %d not supported" % request.request_pgn)

    def commanded_address_request(self, msg: NMEA2000Msg):
        _logger.debug("Commanded address request for address %d" % self._address)
        request = CommandedAddress(message=msg)
        if request.name != self._iso_name:
            _logger.error("Commanded request rejected => No matching names R(%016X) A(%016X)" %
                          (request.name.int_value, self._iso_name.int_value))
            return
        _logger.info("Commanded address => success")
        self.change_address(request.commanded_address)

    def send_product_information(self):
        self._product_information.sa = self._address
        _logger.debug("Send product information from address %d" % self._address)
        self._controller.CAN_interface.send(self._product_information.message(), force_send=True)

    def receive_data_msg(self, msg: NMEA2000Msg):
        _logger.critical("Missing receive_data_msg in class %s" % self.__class__.__name__)
        raise NotImplementedError("Missing receive_data_msg")

    def receive_iso_msg(self, msg: NMEA2000Msg):
        '''
        That method processed ISO messages that have a DA=255
        '''
        _logger.debug("Receive ISO message from address %d PGN %d" % (msg.sa, msg.pgn))
        try:
            self._process_broadcast_vector[msg.pgn](msg)
        except KeyError:
            _logger.debug("Receive ISO message => No handler for device %d on PGN %d" % (self._address, msg.pgn))

    def remote_address_claim(self, msg):
        _logger.debug("Receive address claim from address %d" % msg.sa)
        device = self._controller.get_device_by_address(msg.sa)
        if device.product_information is None:
            self.send_iso_request(msg.sa, 126996)
            self.send_iso_request(msg.sa, 126998)

    def send_iso_request(self, da: int, pgn: int):
        _logger.debug("Sending ISO request for PGN %d to address %d" % (pgn, da))
        request = ISORequest(self._address, da, pgn)
        self._controller.CAN_interface.send(request.message(), force_send=True)

    def send_configuration_information(self):
        _logger.debug("Sending configuration information for address %d" % self._address)
        self._configuration_information.sa = self._address
        self._controller.CAN_interface.send(self._configuration_information.message(), force_send=True)

    def group_function_handler(self, msg: NMEA2000Msg):
        '''
        Handle PGN 126408 Group Function handler
        '''
        group_function = create_group_function(message=msg)
        _logger.debug("Received Group Function for address %d function=%d on PGN %d" % (self._address,
                                                                                        group_function.function,
                                                                                        group_function.function_pgn))
        if type(group_function) is CommandGroupFunction and group_function.pgn_class is not None:
            # ok supported
            acknowledge = AcknowledgeGroupFunction(pgn=group_function.function_pgn, pgn_error_code=0)
            self.process_command_group_function(group_function, acknowledge)
        else:
            acknowledge = AcknowledgeGroupFunction(pgn=group_function.function_pgn, pgn_error_code=1)
        acknowledge.sa = self._address
        acknowledge.da = msg.sa
        _logger.debug("Group Function sending acknowledgement => %s" % acknowledge.message())
        self._controller.CAN_interface.send(acknowledge.message())

    def process_command_group_function(self, group_function, acknowledge):
        if group_function.function_pgn == 60928:
            _logger.debug("Command Group Function on name %s" % self._iso_name)
            group_function.pgn_class.execute_command_parameters(self._iso_name, group_function.parameters, acknowledge)
            _logger.debug("Command Group Function new name %s" % self._iso_name)
        elif group_function.function_pgn == 126998:
            group_function.pgn_class.execute_command_parameters(self._configuration_information,
                                                                group_function.parameters, acknowledge)
        else:
            _logger.error("Command Group Function PGN %d not supported" % group_function.function_pgn)














