#-------------------------------------------------------------------------------
# Name:        gnss_input_service
# Purpose:     gRPC service taking GNSS NMEA2000 messages to formard them to the NMEA2000 bus
#
# Author:      Laurent Carré
#
# Created:     12/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import queue


from navigation_server.generated.gnss_pb2_grpc import add_GNSS_InputServicer_to_server, GNSS_InputServicer
from navigation_server.generated.nmea_messages_pb2 import server_resp
from navigation_server.generated.nmea2000_pb2 import nmea2000pb
from navigation_server.router_core import NMEA2000Msg, Coupler, CouplerTimeOut, CouplerOpenRefused
from navigation_server.can_interface import NMEA2000Application
from navigation_server.router_common import GrpcService, GrpcServerError, NavGenericMsg, N2K_MSG, resolve_ref, SocketCanError

_logger = logging.getLogger("ShipDataServer."+__name__)


class GNSS_InputServicerImpl(GNSS_InputServicer):

    def __init__(self, callback):
        self._callback = callback

    def gnss_message(self, request_iterator, context):

        resp = server_resp()
        _logger.info("GNSS Input stream starts")
        try:
            for msg in request_iterator:
                self._callback(msg)
        except Exception as err:
            _logger.error(f"GNSS Input processing error:{err}")
            resp.reportCode = 101
            resp.status = str(err)
        else:
            _logger.info("GNSS Input processing stream ends")
            resp.reportCode = 0
        return resp


class GNSSInput(NMEA2000Application, GrpcService):
    """
    Hybrid Service/Application shall be declared in the service section and added as application in the N2KActiveController definition
    """

    def __init__(self, opts):
        GrpcService.__init__(self, opts)
        self._servicer = None
        self._requested_address = opts.get('address', int, -1)
        self._forward = opts.get('forward_upstream', bool, True)
        self._can_controller = None
        self._output_queue: queue.Queue = None
        self._lost_msg = 0
        self._can_ready = True

    def device_class_function(self):
        return 60, 145

    def finalize(self):
        try:
            GrpcService.finalize(self)
        except GrpcServerError:
            return
        _logger.info("Adding service %s to server" % self._name)
        self._servicer = GNSS_InputServicerImpl(self.receive_input_msg)
        add_GNSS_InputServicer_to_server(self._servicer, self.grpc_server)

    def init_product_information(self):
        '''
        Specific for GNSS
        '''
        self._product_information.nmea2000_version = 2100
        self._product_information.product_code = 1227
        self._product_information.set_product_information('STNC800 GNSS',
                                                          'Version 1.0',
                                                          'GNSS Sterwen Technology', '00001')
        self._product_information.certification_level = 1
        self._product_information.load_equivalency = 1

    def set_controller(self, controller):
        super().__init__(controller, self._requested_address)
        self._can_controller = controller

    def bus_ready_callback(self):
        _logger.info("GNSS Input - bus ready")
        self._can_ready = True

    def receive_input_msg(self, msg: nmea2000pb):
        """
        Receive a protobuf message and send it to the CAN bus
        Messages received before the CAN is ready are discarded
        """
        n2k_msg = None
        _logger.debug("GNSSInput receive_msg %d %d %d" % (msg.pgn, msg.priority, msg.sa))
        if self._can_controller is not None:
            n2k_msg = NMEA2000Msg(msg.pgn, protobuf=msg)
            n2k_msg.sa = self._address
            if self._can_ready:
                try:
                    self._can_controller.CAN_interface.send(n2k_msg)
                except SocketCanError as err:
                    _logger.error(f"GNSS Input - SocketCanError {err}")
                    if self._can_controller.CAN_interface.is_bus_ready():
                        _logger.error("GNSS Input - bus ready, but still error")
                        raise
                    else:
                        _logger.error("GNSS Input - bus not ready, stopping sending message")
                        self._can_ready = False
                        self._can_controller.CAN_interface.register_read_callback(self.bus_ready_callback)
                        return

            if self._forward:
                # if the forward flag is true, the message is also sent for direct local distribution
                self._can_controller.process_msg(n2k_msg)

        if self._output_queue is not None:
            if n2k_msg is None:
                n2k_msg = NMEA2000Msg(msg.pgn, protobuf=msg)
                n2k_msg.sa = self._address
            try:
                self._output_queue.put(n2k_msg, block=True, timeout=1.0)
                self._lost_msg = 0
            except queue.Full:
                _logger.info("GNSS GRPC Input - output queue full discarding message")
                self._lost_msg += 1
                if self._lost_msg > 20:
                    _logger.error("GNSS GRPC Input - Output queue blocked - removing")
                    self._output_queue = None

    def subscribe(self, output_queue: queue.Queue):
        self._output_queue = output_queue



class GNSSInputCoupler(Coupler):
    """
    This the coupler for messages coming from the GNSS service
    """
    def __init__(self, opts):
        super().__init__(opts)
        self._service_name = opts.get('gnss_input', str, None)
        if self._service_name is None:
            raise ValueError
        self._service = None
        self._mode = self.NMEA2000
        self._direction = self.READ_ONLY
        self._input_queue = queue.Queue(20)

    def open(self) -> bool:
        try:
            self._service = resolve_ref(self._service_name)
            self._service.subscribe(self._input_queue)
            return True
        except KeyError:
            return False

    def _read(self) -> NavGenericMsg:
        try:
            n2k_msg = self._input_queue.get(block=True, timeout=2.0)
            return NavGenericMsg(N2K_MSG, msg=n2k_msg)
        except queue.Empty:
            raise CouplerTimeOut

    def stop(self):
        super().stop()

    def close(self):
        pass



