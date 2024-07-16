#-------------------------------------------------------------------------------
# Name:        mppt_instrument
# Purpose:     classes to manage Victron MPPT as an coupler
#
# Author:      Laurent Carré
#
# Created:     31/03/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import grpc
from generated.energy_pb2 import *
from generated.energy_pb2_grpc import *
import logging
from router_common.protobuf_utilities import *

_logger = logging.getLogger("MPPTDataClient"+"."+__name__)


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


class MPPT_Client:

    def __init__(self, server):
        self._server = server
        self._channel = grpc.insecure_channel(self._server)
        self._stub = solar_mpptStub(self._channel)
        _logger.info("MPPT server stub created on %s" % self._server)
        self._req_id = 0

    def getDeviceInfo(self) -> MPPT_device_proxy:
        _logger.debug("Client GetDeviceInfo")
        try:
            self._req_id += 1
            req = request()
            req.id = self._req_id
            device = self._stub.GetDeviceInfo(req)
            # print(device)
            return MPPT_device_proxy(device)
        except grpc.RpcError as err:
            _logger.error(err)
            return None

    def getOutput(self) -> MPPT_output_proxy:
        _logger.debug("Client GetOutput")
        try:
            self._req_id += 1
            req = request()
            req.id = self._req_id
            output = self._stub.GetOutput(req)
            # print(output)
            return MPPT_output_proxy(output)
        except grpc.RpcError as err:
            _logger.error(err)
            return None

    def server_status(self):
        return self.getDeviceInfo()





