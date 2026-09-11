#-------------------------------------------------------------------------------
# Name:        mppt_instrument
# Purpose:     classes to manage Victron MPPT as an coupler
#
# Author:      Laurent Carré
#
# Created:     31/03/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

import grpc

from navigation_server.generated.energy_pb2_grpc import MPPTServiceStub
from navigation_server.generated.energy_pb2 import MPPT_device, energy_request
from navigation_server.router_common import GrpcClient, ServiceClient, GrpcAccessException, pb_enum_string


_logger = logging.getLogger("ShipDataServer." + __name__)

class MPPT_device_proxy:

    def __init__(self, device: MPPT_device):
        self._device = device

    @property
    def product_id(self):
        return self._device.product_id

    @property
    def firmware(self):
        return self._device.firmware

    @property
    def serial(self):
        return self._device.serial

    @property
    def error(self):
        return pb_enum_string(self._device, 'error', self._device.error)

    @property
    def state(self):
        return pb_enum_string(self._device, 'state', self._device.state)

    @property
    def mppt_state(self):
        return pb_enum_string(self._device, 'mppt_state', self._device.mppt_state)

    @property
    def day_max_power(self) -> float:
        return self._device.day_max_power

    @property
    def day_yield(self) -> float:
        return self._device.day_power


class MPPT_output_proxy:

    def __init__(self, output):
        self._output = output

    @property
    def current(self) -> float:
        return self._output.current

    @property
    def voltage(self) -> float:
        return self._output.voltage

    @property
    def panel_power(self) -> float:
        return self._output.panel_power

    @property
    def panel_voltage(self) -> float:
        return self._output.panel_voltage



class MPPT_Client(ServiceClient):


    def __init__(self):
        super().__init__(MPPTServiceStub)

    def _rpc(self, rpc_func, request, response_class):
        """Invoke an MPPT RPC directly on the stub.

        energy_request declares 'request_id' (not 'id'), so it is incompatible
        with GrpcClient.server_call which assigns req.id. This helper mirrors
        server_call's error handling (GrpcAccessException on UNAVAILABLE) but
        skips the request-id assignment, keeping the connection-state side
        effects of the underlying GrpcClient.
        """
        if self._server is None:
            _logger.error("Attempt to call MPPT service not attached to a server")
            raise GrpcAccessException
        try:
            response = rpc_func(request)
            return response_class(response) if response_class is not None else response
        except grpc.RpcError as err:
            if err.code() == grpc.StatusCode.UNAVAILABLE:
                _logger.error(f"Error accessing server:{err.details()}")
                self._server._state = GrpcClient.NOT_CONNECTED
            else:
                _logger.info(f"client_common server call => Server error:{err.details()}")
            raise GrpcAccessException

    def getDeviceInfo(self) -> MPPT_device_proxy:
        _logger.debug("Client GetDeviceInfo")
        return self._rpc(self._stub.GetDeviceInfo, energy_request(), MPPT_device_proxy)

    def getOutput(self) -> MPPT_output_proxy:
        _logger.debug("Client GetOutput")
        return self._rpc(self._stub.GetOutput, energy_request(), MPPT_output_proxy)

    def getTrend(self):
        _logger.debug("Client GetTrend")
        trend = self._rpc(self._stub.GetTrend, energy_request(), None)
        _logger.debug("Trend response with %d values" % trend.nb_values)
        return trend

    def server_status(self):
        if self.server_state() == GrpcClient.NOT_CONNECTED:
            self._server.connect()
        return self.getDeviceInfo()





