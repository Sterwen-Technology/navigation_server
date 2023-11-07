# -------------------------------------------------------------------------------
# Name:        NMEA2K-controller
# Purpose:     Analyse and process NMEA2000 network control messages with CAN access
#
# Author:      Laurent Carré
#
# Created:     02/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import queue

from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea2000.nmea2k_controller import NMEA2KController
from nmea2000.nmea2k_application import NMEA2000Application
from nmea2000.nmea2k_can_interface import SocketCANInterface, SocketCanError
from utilities.global_exceptions import ObjectCreationError

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2KActiveController(NMEA2KController):

    def __init__(self, opts):

        super().__init__(opts)
        self._channel = opts.get('channel', str, 'can0')
        self._trace = opts.get('trace', bool, False)
        try:
            self._can = SocketCANInterface(self._channel, self._input_queue, self._trace)
        except SocketCanError as e:
            _logger.error(e)
            raise ObjectCreationError(str(e))
        self._coupler_queue = None
        self._applications = {}
        self.add_application(NMEA2000Application(self, opts))

    def start(self):
        self._can.start()
        super().start()
        self.start_applications()

    def stop(self):
        self._can.stop()
        super().stop()

    def set_coupler_queue(self, coupler_queue):
        self._coupler_queue = coupler_queue

    @property
    def CAN_interface(self):
        return self._can

    def add_application(self, application):
        self._devices[application.address] = application
        self._applications[application.address] = application
        self._can.add_address(application.address)

    def change_application_address(self, application, old_address):
        # application must already be initialized with the target address
        self.remove_application(old_address)
        self.add_application(application)

    def remove_application(self, old_address: int):
        self.delete_device(old_address)
        self._can.remove_address(old_address)
        del self._applications[old_address]

    def start_applications(self):
        _logger.debug("NMEA2000 Applications starts")
        for app in self._applications.values():
            app.start()

    def process_msg(self, msg: NMEA2000Msg):
        if msg.da != 255:
            # we have a da, so call the application
            try:
                self._applications[msg.da].receive_msg(msg)
            except KeyError:
                _logger.error("Wrongly routed message for destination %d pgn %d" % (msg.da, msg.pgn))
                return
        elif msg.is_iso_protocol:
            super().process_msg(msg)
        else:
            if self._coupler_queue is not None:
                try:
                    self._coupler_queue.put(msg, block=False)
                except queue.Full:
                    _logger.error("CAN controller %s Coupler queue full - message lost")

