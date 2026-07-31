#-------------------------------------------------------------------------------
# Name:        NMEA2000 / CAN client
# Purpose:     Access to gRPC NMEA2000/CAN Service
#
# Author:      Laurent Carré
#
# Created:     06/05/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.generated.nmea2000_service_pb2_grpc import Nmea2000ControllerServiceStub
from navigation_server.generated.nmea2000_service_pb2 import N2KDeviceMsg, Nmea2000ControllerMsg, Nmea2000Request, PGN_definition

from navigation_server.router_common import ServiceClient, ProtobufProxy, GrpcAccessException

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KDeviceProxy(ProtobufProxy):

    def __init__(self, msg: N2KDeviceMsg):
        super().__init__(msg)

    @property
    def manufacturer_name(self):
        return self._msg.iso_name.manufacturer_name

    @property
    def product_name(self):
        return self._msg.product_information.model_id

    @property
    def description(self):
        return self._msg.product_information.model_serial_code


class NMEA2000CanControllerProxy(ProtobufProxy):

    def __init__(self, msg:Nmea2000ControllerMsg):
        super().__init__(msg)

    @property
    def devices(self) -> list[N2KDeviceProxy]:
        resp = []
        for dev in self._msg.devices:
            resp.append(N2KDeviceProxy(dev))
        return resp


class NMEA2000CanClient(ServiceClient):

    def __init__(self):
        super().__init__(Nmea2000ControllerServiceStub)

    def get_status(self, cmd=None) -> NMEA2000CanControllerProxy:
        req = Nmea2000Request()
        if cmd is not None:
            req.cmd = cmd
        return self._server_call(self._stub.GetStatus, req, NMEA2000CanControllerProxy)

    def get_device(self, device_address) -> N2KDeviceProxy:
        req = Nmea2000Request()
        req.device = device_address

        return self._server_call(self._stub.GetDeviceStatus, req, N2KDeviceProxy)

    def get_pgn_definition(self, pgn:int) -> str:
        req = Nmea2000Request()
        req.pgn = pgn
        resp = self._server_call(self._stub.GetPgnDefinition, req, None)
        return resp.definition


    def stop_trace(self):
        req = Nmea2000Request()
        return self._server_call(self._stub.StopTrace, req, NMEA2000CanControllerProxy)

    def start_trace(self, trace_name):
        req = Nmea2000Request()
        req.cmd = trace_name
        return self._server_call(self._stub.StartTrace, req, NMEA2000CanControllerProxy)






