#-------------------------------------------------------------------------------
# Name:        NMEA2K-controller
# Purpose:     Analyse and process NMEA2000 network control messages
#
# Author:      Laurent Carré
#
# Created:     21/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import threading
import queue

from nmea_routing.server_common import NavigationServer
from nmea_routing.nmea2000_msg import NMEA2000Msg

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NMEA2KController(NavigationServer, threading.Thread):

    def __init__(self, opts):
        super().__init__(opts)
        threading.Thread.__init__(self, name=self._name)
        queue_size = opts.get('queue_size', int, 20)
        self._input_queue = queue.Queue(queue_size)
        self._stop_flag = False
        _logger.info("%s debug level %d" % (__name__, _logger.getEffectiveLevel()))

    def server_type(self):
        return 'NMEA200_CONTROLLER'

    def send_message(self, msg: NMEA2000Msg):
        try:
            self._input_queue.put(msg, block=False)
        except queue.Full:
            _logger.warning("NMEA2000 Controller input queue full")

    def run(self) -> None:
        _logger.info("%s NMEA2000 Controller starts" % self._name)
        while not self._stop_flag:
            try:
                msg = self._input_queue.get(block=True, timeout=1.0)
            except queue.Empty:
                continue
            _logger.debug("NMEA Controller input %s" % msg.format1())
            # further processing here

        _logger.info("%s NMEA2000 Controller stops" % self._name)

    def stop(self):
        self._stop_flag = True
