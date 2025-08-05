#-------------------------------------------------------------------------------
# Name:        gnss_coupler
# Purpose:     implementation of GNSS NMEA0183 GNSS interface - some features are specific to Ublox
#
# Author:      Laurent Carré
#
# Created:     10/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import queue

from navigation_server.router_core import Coupler, NMEA0183Msg, CouplerTimeOut
from navigation_server.router_common import NavGenericMsg, resolve_ref
from navigation_server.gnss.gnss_service import N0183Subscriber


_logger = logging.getLogger("ShipDataServer."+__name__)


class GNSSCoupler(Coupler):

    def __init__(self, opts):

        super().__init__(opts)

        self._formatters = opts.getlist('formatters', str, ['RMC', 'GGA'])
        self._formatters = list(fmt.encode() for fmt in self._formatters)
        self._service_name = opts.get('gnss_service', str, None)
        if self._service_name is None:
            raise ValueError
        self._service = None
        self._mode = self.NMEA0183
        self._direction = self.READ_ONLY
        self._input_queue = queue.Queue(10)


    def open(self) -> bool:
        """
        Open the link and start the reading flow
        """
        try:
            self._service = resolve_ref(self._service_name)
        except KeyError:
            _logger.error(f"GNSSCoupler unknown service {self._service_name}")
            return False
        self._service.add_n0183_subscriber(N0183Subscriber(self._formatters, self._input_queue))
        return True

    def stop(self):
        super().stop()

    def close(self):
        self._service.clear_n0183_subscriber()

    def _read(self) -> NavGenericMsg:
        try:
            return self._input_queue.get(block=True, timeout=1.0)
        except queue.Empty:
            _logger.debug("GNSS Coupler time out")
            raise CouplerTimeOut





