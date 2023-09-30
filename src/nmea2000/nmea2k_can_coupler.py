# -------------------------------------------------------------------------------
# Name:        NMEA2K-CAN Coupler class
# Purpose:     Implements the direct CAN Coupler
#
# Author:      Laurent Carré
#
# Created:     12/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import queue

from nmea_routing.coupler import Coupler, CouplerTimeOut, CouplerWriteError
from nmea2000.nmea2k_controller import NMEA2KActiveController
from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea_routing.generic_msg import NavGenericMsg, N2K_MSG

_logger = logging.getLogger("ShipDataServer." + __name__)


class DirectCANCoupler(Coupler):

    def __init__(self, opts):

        super().__init__(opts)

        if self._n2k_ctlr_name is None:
            _logger.critical("DirectCANCoupler mus have an associated NMEA2000 Controller")
            raise ValueError
        self._in_queue = queue.Queue(20)
        self.address = 0

    def open(self):

        if not isinstance(self._n2k_controller, NMEA2KActiveController):
            _logger.critical("Incorrect NMEAController for DirectCAN")
            return False

        self._n2k_controller.CAN_interface.set_data_queue(self._in_queue)
        return True

    def stop(self):
        self._n2k_controller.CAN_interface.set_data_queue(None)
        super().stop()

    def close(self):
        pass

    def total_msg_raw(self):
        return self._n2k_controller.CAN_interface.total_msg_raw()

    def read(self) -> NavGenericMsg:
        '''
        the read method is redefined as it is much simplified in that case
        only NMEA2000 message and iso/data already sorted out
        '''
        try:
            msg = self._in_queue.get(timeout=1.0)
        except queue.Empty:
            raise CouplerTimeOut

        msg = NavGenericMsg(N2K_MSG, msg=msg)
        self.trace(self.TRACE_IN, msg)
        # _logger.debug("Read:%s", msg)
        if self._data_sink is not None:
            self._data_sink.send_msg(msg)
        return msg

    def define_n2k_writer(self):
        return None

    def send_msg_gen(self, msg: NavGenericMsg):
        if msg.type != N2K_MSG:
            raise CouplerWriteError("CAN coupler only accepts NMEA2000 messages")

        if self._direction == self.READ_ONLY:
            _logger.error("Coupler %s attempt to write on a READ ONLY coupler" % self.name())
            return False
        self._total_msg_s += 1
        return self.send(msg.msg)

    def send(self, msg: NMEA2000Msg):
        return self._n2k_controller.CAN_interface.send(msg)
