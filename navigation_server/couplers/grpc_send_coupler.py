#-------------------------------------------------------------------------------
# Name:        grpc_nmea_coupler
# Purpose:      coupler sending NMEA2000 streams to the CAN server
#
# Author:      Laurent Carré
#
# Created:     12/06/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import queue

from navigation_server.router_core import Coupler, CouplerTimeOut
from navigation_server.router_common import N2K_MSG, NavGenericMsg
from router_common import GrpcClient, ServiceClient

_logger = logging.getLogger("ShipDataServer."+__name__)


class GrpcSendStreamCoupler(Coupler, ServiceClient):

    def __init__(self, opts):

        super().__init__(opts)
        # create the server
        self._direction = self.WRITE_ONLY # that is a mono directional coupler
        self._mode = self.NMEA2000
        self._target_server = opts.get('target_server', str, None)
        if self._target_server is None:
            _logger.error(f"GrpcSendStreamCoupler {self.object_name()} missing target_server")
            raise ValueError
        self._target_port = opts.get('target_port', int, 0)
        if self._target_port == 0:
            _logger.error(f"GrpcSendStreamCoupler {self.object_name()} missing target_port")
            raise ValueError
        
    def open(self):
        _logger.debug("GrpcNmeaCoupler %s open" % self.object_name())
        self._service.finalize()
        self._service.open()
        self._state = self.CONNECTED
        return True


