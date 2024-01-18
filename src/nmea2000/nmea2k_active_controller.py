# -------------------------------------------------------------------------------
# Name:        NMEA2K-controller
# Purpose:     Analyse and process NMEA2000 network control messages with CAN access
#
# Author:      Laurent Carré
#
# Created:     02/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea2000.nmea2k_controller import NMEA2KController
from nmea2000.nmea2k_application import NMEA2000Application, NMEA2000ApplicationPool
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
        self._apool = NMEA2000ApplicationPool(self, opts)
        self._application_names = opts.getlist('applications', str, None)
        self._address_change_request = None

    def start(self):
        if self._application_names is not None:
            for ap_name in self._application_names:
                ap = self.resolve_direct_ref(ap_name)
                if ap is not None:
                    _logger.debug("CAN active controller adding application:%s" % ap_name)
                    if issubclass(ap.__class__, NMEA2000Application):
                        ap.set_controller(self)
                        self.add_application(ap)
                    else:
                        _logger.error("Invalid application for CAN Controller (ECU) => ignored")

        if len(self._applications) == 0:
            _logger.info("Creating default application")
            self.add_application(NMEA2000Application(self))
        _logger.debug("Starting CAN bus")
        self._can.start()
        super().start()
        self.start_applications()

    def stop(self):
        self._can.stop()
        super().stop()

    @property
    def CAN_interface(self):
        return self._can

    @property
    def app_pool(self) -> NMEA2000ApplicationPool:
        return self._apool

    def add_application(self, application):
        self._devices[application.address] = application
        self._applications[application.address] = application
        self._can.add_address(application.address)

    def apply_change_application_address(self):
        # application must already be initialized with the target address
        self.remove_application(self._address_change_request[1])
        self.add_application(self._address_change_request[0])
        self._address_change_request = None

    def change_application_address(self, application, old_address):
        assert self._address_change_request is None
        self._address_change_request = (application, old_address)

    def remove_application(self, old_address: int):
        self.delete_device(old_address)
        self._can.remove_address(old_address)
        del self._applications[old_address]

    def start_applications(self):
        _logger.debug("NMEA2000 Controller => Applications starts")
        for app in self._applications.values():
            app.start_application()

    def process_msg(self, msg: NMEA2000Msg):
        _logger.debug("CAN data received sa=%d PGN=%d da=%d" % (msg.sa, msg.pgn, msg.da))
        if msg.da != 255:
            # we have a da, so call the application
            try:
                if msg.is_iso_protocol:
                    self._applications[msg.da].receive_msg(msg)
                else:
                    self._applications[msg.da].receive_data_msg(msg)
            except KeyError:
                _logger.error("Wrongly routed message for destination %d pgn %d" % (msg.da, msg.pgn))
                return
        else:
            if msg.is_iso_protocol:
                super().process_msg(msg)    # proxy treatment
                # need also to process broadcast (DA=255) messages
                for application in self._applications.values():
                    application.receive_iso_msg(msg)
                if self._address_change_request is not None:
                    # address change cannot be applied on the fly
                    self.apply_change_application_address()
            else:
                _logger.debug("Active controller message dispatch sa=%d pgn =%d" % (msg.sa, msg.pgn))
                for application in self._applications.values():
                    application.receive_data_msg(msg)



