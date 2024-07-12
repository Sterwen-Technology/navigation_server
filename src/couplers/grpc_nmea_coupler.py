#-------------------------------------------------------------------------------
# Name:        grpc_nmea_coupler
# Purpose:      coupler taking inputs on grpc via server NMEA2000 and NMEA0183
#
# Author:      Laurent Carré
#
# Created:     23/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import queue

from nmea2000 import GrpcDataService
from router_core import Coupler, CouplerTimeOut
from router_core import NMEA0183Msg
from router_common import N2K_MSG, N0183D_MSG, NavGenericMsg

_logger = logging.getLogger("ShipDataServer."+__name__)


class GrpcNmeaCoupler(Coupler):

    def __init__(self, opts):

        super().__init__(opts)
        # create the server
        self._decode_n2k = opts.get('decoded_nmea2000', bool, False)
        if self._decode_n2k:
            self._service = GrpcDataService(opts, self.n2k_msg_in, self.nmea0183_msg_in, self.decoded_nmea_in)
        else:
            self._service = GrpcDataService(opts, self.n2k_msg_in, self.nmea0183_msg_in)
        self._queue = queue.Queue(20)
        self._direction = self.READ_ONLY  # that is a mono directional coupler

    def open(self):
        _logger.debug("GrpcNmeaCoupler %s open" % self.object_name())
        self._service.finalize()
        self._service.open()
        self._state = self.CONNECTED
        return True

    def stop_communication(self):
        self._service.close()

    def close(self):
        self._service.close()

    def nmea0183_msg_in(self, msg):

        if type(msg) is NMEA0183Msg:
            push_msg = msg
        else:
            push_msg = NavGenericMsg(N0183D_MSG, msg=msg)
        self.push_message(push_msg)

    def n2k_msg_in(self, msg):
        self.push_message(NavGenericMsg(N2K_MSG, msg=msg))

    def decoded_nmea_in(self, msg):
        self.push_message(msg)

    def push_message(self, msg):
        try:
            self._queue.put(msg, block=False)
        except queue.Full:
            _logger.error("GrpcCoupler %s input queue full - message lost" % self.object_name())

    def _read(self):
        try:
            return self._queue.get(timeout=5.0)
        except queue.Empty:
            raise CouplerTimeOut

