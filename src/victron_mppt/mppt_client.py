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
from generated.vedirect_pb2 import *
from generated.vedirect_pb2_grpc import *
import logging

_logger = logging.getLogger("MPPTDataClient"+"."+__name__)


class MPPT_device_proxy:

    def __init__(self, device: MPPT_device):
        self._device = device

    @property
    def product_id(self):
        return self._device.product_id



class MPPT_Client:

    def __init__(self, opts):
        self._address = opts.address
        self._port = opts.port
        self._server = "%s:%d" % (self._address, self._port)
        self._channel = grpc.insecure_channel(self._server)
        self._stub = solar_mpptStub(self._channel)
        _logger.info("MPPT server stub created on %s" % self._server)
        self._req_id = 0

    def getDeviceInfo(self):
        _logger.debug("Client GetDeviceInfo")
        try:
            self._req_id += 1
            req = request()
            request.id = self._req_id
            device = self._stub.GetDeviceInfo(req)
            return device
        except grpc.RpcError as err:
            print(err)
            return None

    def server_status(self):
        return self.getDeviceInfo()





