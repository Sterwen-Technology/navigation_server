#-------------------------------------------------------------------------------
# Name:        grpc_input_application
# Purpose:     CAN CA taking Grpc input for messages
#
# Author:      Laurent Carré
#
# Created:     14/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from nmea2000.nmea2k_application import NMEA2000Application
from nmea_routing.grpc_nmea_input_server import GrpcDataServer
from nmea2000.generated_base import NMEA2000DecodedMsg


_logger = logging.getLogger("ShipDataServer." + __name__)


class GrpcInputApplication(GrpcDataServer, NMEA2000Application):

    def __init__(self, opts):

        GrpcDataServer.__init__(self, opts, callback_pb=self.input_message)
        self._controller_name = opts.get('controller', str, None)

    def start_application(self):
        GrpcDataServer.start(self)
        super().start_application()

    def set_controller(self, controller):
        self._controller = controller
        NMEA2000Application.__init__(self, controller)

    def input_message(self, msg: NMEA2000DecodedMsg):
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





