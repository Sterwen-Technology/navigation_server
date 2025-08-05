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

from navigation_server.router_core import Coupler, CouplerTimeOut, CouplerWriteError
# from navigation_server.nmea2000.nmea2k_active_controller import NMEA2KActiveController
from .nmea2k_application import NMEA2000Application
from navigation_server.router_core import NMEA2000Msg
from navigation_server.router_common import NavGenericMsg, N2K_MSG
from navigation_server.router_common import get_global_var, set_global_var

_logger = logging.getLogger("ShipDataServer." + __name__)


class DirectCANCoupler(Coupler, NMEA2000Application):

    def __init__(self, opts):

        super().__init__(opts)
        self._in_queue = queue.Queue(40)
        self._mode_str = "nmea2000"
        self._mode = self.NMEA2000
        self._controller_set = False

    def set_controller(self, controller):
        _logger.debug("Direct CAN coupler %s initializing controller" % self.object_name())
        NMEA2000Application.__init__(self, controller)
        self._controller_set = True
        set_global_var(f'{self.object_name()}.controller', controller)
        controller.set_pgn_vector(self, -1) # catch all

    def restart(self):
        _logger.debug("DirectCANCoupler %s restart" % self.object_name())
        controller = get_global_var(f'{self.object_name()}.controller')
        if controller is not None:
            self.set_controller(controller)

    def open(self):
        _logger.debug("DirectCANCoupler %s open" % self.object_name())
        if self._controller_set:
            self._controller.CAN_interface.wait_for_bus_ready()
            _logger.debug("DirectCANCoupler CAN bus ready")
            return True
        else:
            _logger.error("Coupler %s CAN controller not ready" % self.object_name())
            return False

    def stop(self):
        super().stop()

    def close(self):
        pass

    def total_msg_raw(self) -> int:
        return self._controller.CAN_interface.total_msg_raw()

    def receive_data_msg(self, msg: NMEA2000Msg):
        """
        This method is called when a full NMEA2000 message is received
        Overload from NMEA2000Application
        """
        try:
            self._in_queue.put(msg, timeout=0.1)
        except queue.Full:
            _logger.error(f"CAN Coupler {self.object_name()} receive queue full - discarding message with PGN {msg.pgn}")

    def read(self) -> NavGenericMsg:
        """
        the read method is redefined as it is much simplified in that case
        only NMEA2000 message and iso/data already sorted out
        now it is a generator that is emptying the queue
        """
        def process_msg(m) -> NavGenericMsg:
            # _logger.debug("Direct CAN read %s" % m.format1())
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
        """
        Send a NMEA2000 message on the CAN bus
        """
        if msg.type != N2K_MSG:
            raise CouplerWriteError("CAN coupler only accepts NMEA2000 messages")

        if self._direction == self.READ_ONLY:
            _logger.error("Coupler %s attempt to write on a READ ONLY coupler" % self.object_name())
            return False
        self._total_msg_s += 1
        return self.send(msg.msg)

    def send(self, msg: NMEA2000Msg):
        """
        Send the NMEA2000 message to the bus interface
        """
        return self._send_to_bus(msg)

    def stop_trace(self):
        if self._controller_set:
            self._controller.CAN_interface.stop_trace()
        super().stop_trace()
