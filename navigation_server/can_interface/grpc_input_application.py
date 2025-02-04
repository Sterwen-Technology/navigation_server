#-------------------------------------------------------------------------------
# Name:        grpc_input_application
# Purpose:     CAN CA taking Grpc input for messages
#
# Author:      Laurent Carré
#
# Created:     14/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from .nmea2k_application import NMEA2000Application
from navigation_server.nmea2000_datamodel import NMEA2000DecodedMsg
from navigation_server.nmea2000 import GrpcDataService
from navigation_server.router_core import NMEA2000Msg


_logger = logging.getLogger("ShipDataServer." + __name__)


class GrpcInputApplication(GrpcDataService, NMEA2000Application):

    def __init__(self, opts):
        GrpcDataService.__init__(self, opts, callback_pb=self.input_message_pb, callback_n2k=self.input_message)
        self._controller_name = opts.get('controller', str, None)

    def start_application(self):
        _logger.debug("GrpcInputApplication => start")
        GrpcDataService.finalize(self)
        super().start_application()
        super().open()

    def set_controller(self, controller):
        self._controller = controller
        NMEA2000Application.__init__(self, controller)

    def input_message_pb(self, msg: NMEA2000DecodedMsg):
        _logger.debug("Grpc Input application receiving PGN %d" % msg.pgn)
        # convert it into a message for the CAN bus
        # adjust SA
        msg.sa = self._address
        try:
            can_message = msg.message()
        except Exception as err:
            _logger.error("Error coding CAN message for PGN %d: %s" % (msg.pgn, err))
            raise
        self._controller.CAN_interface.send(can_message)

    def input_message(self, msg: NMEA2000Msg):
        msg.sa = self._address
        self._controller.CAN_interface.send(msg)

    def receive_data_msg(self, msg: NMEA2000Msg):
        # to be implemented for bi-directional applications
        pass





