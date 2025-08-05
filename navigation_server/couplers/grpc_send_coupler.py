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

from navigation_server.router_core import Coupler, CouplerTimeOut, CouplerWriteError, NMEA2000Msg
from navigation_server.router_common import GrpcClient, ServiceClient, GrpcAccessException
from navigation_server.generated.n2k_can_service_pb2_grpc import CAN_ControllerServiceStub
from navigation_server.generated.n2k_can_service_pb2 import CANSendRequest
from navigation_server.generated.nmea2000_pb2 import nmea2000pb


_logger = logging.getLogger("ShipDataServer."+__name__)


class N2KGrpcSendCoupler(Coupler, ServiceClient):
    """
    Represents a GRPC-based NMEA 2000 message sender coupler.

    This class integrates NMEA 2000 message sending functionality using GRPC. It is a
    mono-directional coupler designed to transmit messages to a target GRPC server. The
    class inherits from Coupler and ServiceClient base classes, allowing extended
    coupling functionality and GRPC service operations. It establishes communication
    with a GRPC server based on the given options and provides a method for sending
    NMEA 2000 messages.

    Attributes:
        _direction: Specifies the direction of the coupler as WRITE_ONLY.
        _mode: Defines the operational mode, which is NMEA2000.
        _n2k_writer: A reference for NMEA 2000 message writing.
        _target_server: The address of the target GRPC server.
        _target_port: The port number of the target GRPC server.
        _device: The device identifier used in communication.
        _state: The current state of the coupler (e.g., CONNECTED, NOT_READY).

    Raises:
        ValueError: Raised if required options 'target_server', 'target_port',
                    or 'device' are not provided or are invalid.
        CouplerWriteError: Raised when a message fails to send due to server error.

    """
    def __init__(self, opts):

        super().__init__(opts)
        # create the server
        self._direction = self.WRITE_ONLY # that is a mono directional coupler
        self._mode = self.NMEA2000
        self._n2k_writer = self
        self._target_server = opts.get('target_server', str, None)
        if self._target_server is None:
            _logger.error(f"GrpcSendStreamCoupler {self.object_name()} missing target_server")
            raise ValueError
        self._target_port = opts.get('target_port', int, 0)
        if self._target_port == 0:
            _logger.error(f"GrpcSendStreamCoupler {self.object_name()} missing target_port")
            raise ValueError
        server = GrpcClient.get_client(f"{self._target_server}:{self._target_port}")
        self._device = opts.get('device', str, None)
        if self._device is None:
            _logger.error(f"GrpcSendStreamCoupler {self.object_name()} missing device")
            raise ValueError
        ServiceClient.__init__(self, CAN_ControllerServiceStub)
        server.add_service(self)
        
    def open(self):
        _logger.debug("GrpcNmeaSenderCoupler %s open" % self.object_name())
        if self.server_connect_wait(5.0):
            _logger.info("GrpcNmeaCoupler %s connected" % self.object_name())
            self._state = self.CONNECTED
            return True
        else:
            _logger.error("GrpcNmeaSenderCoupler %s cannot connect to server %s" % (self.object_name(), self._target_server))
            return False

    def close(self):
        pass

    def send_n2k_msg(self, msg: NMEA2000Msg):
        _logger.debug("GrpcNmeaSenderCoupler %s send PGN=%d" % (self.object_name(), msg.pgn))
        request = CANSendRequest()
        request.device = self._device
        msg.as_protobuf(request.n2k_msg)
        try:
            resp = self._server_call(self._stub.SendNmea2000Msg, request, None)
        except GrpcAccessException:
            self._state = self.NOT_READY
            return
        if resp.error != 0:
            raise CouplerWriteError(f"GrpcNmeaSenderCoupler {self.object_name()} server error {resp.error}")


