# -------------------------------------------------------------------------------
# Name:        NMEA2000 Generic sender device
# Purpose:     Implement a minimum generic device that is sending NMEA2000 messages to the CAN bus
#               Generic J1939 / NMEA2000 functions are inherited
#
# Author:      Laurent Carré
#
# Created:     16/06/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from navigation_server.can_interface import NMEA2000Application
from navigation_server.router_core import NMEA2000Msg

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000SenderDevice(NMEA2000Application):

    def __init__(self, opts):
        self._name = opts['name']
        self._requested_address = opts.get('address', int, -1)
        self._model_id = opts.get('model_id', str, 'Generic Device')
        self._device_class = opts.get('device_class', int, 25)
        self._device_function = opts.get('device_function', int, 130)

    def init_product_information(self):
        super().init_product_information()
        self._product_information.model_id = self._model_id

    def device_class_function(self):
        return self._device_class, self._device_function

    def set_controller(self, controller):
        super().__init__(controller, self._requested_address)
        self._app_name = self._name
        self._controller.register_application(self)
        _logger.info(f"NMEA2000SenderDevice {self.name} ready")

    def receive_data_msg(self, msg: NMEA2000Msg):
        _logger.error(f"Device {self.name} received NMEA2000 message {msg.format2()}")

    def send_message(self, msg: NMEA2000Msg):
        msg.sa = self._address
        self._send_to_bus(msg)
