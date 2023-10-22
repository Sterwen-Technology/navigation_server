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

from nmea_routing.grpc_nmea_reader import GrpcDataServer
from nmea_routing.coupler import Coupler, CouplerTimeOut
from nmea0183.nmea0183_msg import NMEA0183Msg, N2K_MSG, N0183_MSG, N0183D_MSG, NavGenericMsg

_logger = logging.getLogger("ShipDataServer."+__name__)


class GrpcNmeaCoupler(Coupler):

    def __init__(self, opts):

        super().__init__(opts)
        # create the server
        self._server = GrpcDataServer(opts, self.n2k_msg_in, self.nmea0183_msg_in)
        self._queue = queue.Queue(20)
        self._direction = self.READ_ONLY  # that is a mono directional coupler
        self._server_running = False

    def open(self):
        if not self._server_running:
            self._server.start()
            self._server_running = True
        return True

    def stop_communication(self):
        self._server.stop()
        self._server.join()
        self._server_running = False

    def close(self):
        pass

    def nmea0183_msg_in(self, msg):

        if type(msg) is NMEA0183Msg:
            push_msg = msg
        else:
            push_msg = NavGenericMsg(N0183D_MSG, msg=msg)
        self.push_message(push_msg)

    def n2k_msg_in(self, msg):
        self.push_message(NavGenericMsg(N2K_MSG, msg=msg))

    def push_message(self, msg):
        try:
            self._queue.put(msg, block=False)
        except queue.Full:
            _logger.error("GrpcServer %s input queue full - message lost" % self.name())

    def _read(self):
        try:
            return self._queue.get(timeout=5.0)
        except queue.Empty:
            raise CouplerTimeOut

