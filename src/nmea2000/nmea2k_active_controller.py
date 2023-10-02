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
        self._applications = {}
        self.add_application(NMEA2000Application(self, opts))

    def start(self):
        self._can.start()
        super().start()
        self.start_applications()

    def stop(self):
        self._can.stop()
        super().stop()

    @property
    def CAN_interface(self):
        return self._can

    def add_application(self, application):
        self._applications[application.address] = application

    def start_applications(self):
        _logger.debug("NMEA2000 Applications starts")
        for app in self._applications.values():
            app.start()
