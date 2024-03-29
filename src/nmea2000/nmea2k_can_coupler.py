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
# from nmea2000.nmea2k_active_controller import NMEA2KActiveController
from nmea2000.nmea2k_application import NMEA2000Application
from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea_routing.generic_msg import NavGenericMsg, N2K_MSG
from utilities.global_exceptions import ObjectCreationError

_logger = logging.getLogger("ShipDataServer." + __name__)


class DirectCANCoupler(Coupler, NMEA2000Application):

    def __init__(self, opts):

        super().__init__(opts)
        self._in_queue = queue.Queue(20)
        self._mode_str = "nmea2000"
        self._mode = self.NMEA2000
        self._controller_set = False

    def set_controller(self, controller):
        _logger.debug("DirectCANCoupler initializing controller")
        NMEA2000Application.__init__(self, controller)
        self._controller_set = True

    def open(self):
        if self._controller_set:
            self._controller.CAN_iterface.wait_for_bus_ready()
            return True
        else:
            _logger.error("Coupler %s CAN controller not ready" % self.object_name())
            return False

    def stop(self):
        super().stop()

    def close(self):
        pass

    def total_msg_raw(self):
        return self._controller.CAN_interface.total_msg_raw()

    def receive_data_msg(self, msg: NMEA2000Msg):
        try:
            self._in_queue.put(msg, block=False)
        except queue.Full:
            _logger.error("CAN %s queue full - discarding message" % self.object_name())

    def read(self):
        '''
        the read method is redefined as it is much simplified in that case
        only NMEA2000 message and iso/data already sorted out
        now it is a generator that is emptying the queue
        '''
        def process_msg(m):
            _logger.debug("Direct CAN read %s" % m.format1())
            gen_msg = NavGenericMsg(N2K_MSG, msg=m)
            self.trace(self.TRACE_IN, gen_msg)
            return gen_msg

        try:
            msg = self._in_queue.get(timeout=1.0)
        except queue.Empty:
            raise CouplerTimeOut
        yield process_msg(msg)
        # now look for more messages
        while True:
            try:
                msg = self._in_queue.get(block=False)
            except queue.Empty:
                return
            yield process_msg(msg)

    def define_n2k_writer(self):
        return None

    def send_msg_gen(self, msg: NavGenericMsg):
        if msg.type != N2K_MSG:
            raise CouplerWriteError("CAN coupler only accepts NMEA2000 messages")

        if self._direction == self.READ_ONLY:
            _logger.error("Coupler %s attempt to write on a READ ONLY coupler" % self.object_name())
            return False
        self._total_msg_s += 1
        return self.send(msg.msg)

    def send(self, msg: NMEA2000Msg):
        return self._controller.CAN_interface.send(msg)

    def stop_trace(self):
        if self._controller_set:
            self._controller.CAN_interface.stop_trace()
        super().stop_trace()
