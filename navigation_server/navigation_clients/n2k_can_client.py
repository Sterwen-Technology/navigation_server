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

from navigation_server.generated.n2k_can_service_pb2_grpc import CAN_ControllerServiceStub
from navigation_server.generated.n2k_can_service_pb2 import N2KDeviceMsg, CAN_ControllerMsg, CANRequest

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

    def __init__(self, msg:CAN_ControllerMsg):
        super().__init__(msg)

    @property
    def devices(self) -> list[N2KDeviceProxy]:
        resp = []
        for dev in self._msg.devices:
            resp.append(N2KDeviceProxy(dev))
        return resp


class NMEA2000CanClient(ServiceClient):

    def __init__(self):
        super().__init__(CAN_ControllerServiceStub)

    def get_status(self, cmd=None) -> NMEA2000CanControllerProxy:
        req = CANRequest()
        if cmd is not None:
            req.cmd = cmd
        try:
            return self._server_call(self._stub.GetStatus, req, NMEA2000CanControllerProxy)
        except GrpcAccessException:
            return None

    def stop_trace(self):
        req = CANRequest()
        return self._server_call(self._stub.StopTrace, req, NMEA2000CanControllerProxy)

    def start_trace(self, trace_name):
        req = CANRequest()
        req.cmd = trace_name
        return self._server_call(self._stub.StartTrace, req, NMEA2000CanControllerProxy)






