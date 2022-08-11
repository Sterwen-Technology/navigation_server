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

from generated.vedirect_pb2 import *
from generated.vedirect_pb2_grpc import *
from grpc import StatusCode, insecure_channel, RpcError
import logging

_logger = logging.getLogger("MPPTDataServer"+"."+__name__)


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
        self._channel = insecure_channel(self._address)
        self._stub = solar_mpptStub(self._channel)
        self._req_id = 0

    def getDeviceInfo(self):
        try:
            self._req_id += 1
            req = request()
            request.id = self._req_id
            device = self._stub.GetDeviceInfo(req)
            return device
        except RpcError as err:
            print(err)
            return None

    def server_status(self):
        return self.getDeviceInfo()





