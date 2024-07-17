#-------------------------------------------------------------------------------
# Name:        navigation_date_client
# Purpose:     proxy to access the various navigation services
#
# Author:      Laurent Carré
#
# Created:     17/07/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from generated.navigation_data_pb2 import *
from generated.navigation_data_pb2_grpc import *

from router_common import pb_enum_string, ProtobufProxy, GrpcAccessException

_logger = logging.getLogger("ShipDataClient." + __name__)


class EngineProxy(ProtobufProxy):

    def __init__(self, engine_msg: engine_data):
        self._engine = engine_msg

    @property
    def state(self):
        return pb_enum_string(self._engine, 'state', self._engine.state)


    @property
    def last_start_time(self):
        if self._engine.HasField('last_start_time'):
            return self._engine.last_start_time
        else:
            return "Unknown"

    @property
    def last_stop_time(self):
        if self._engine.HasField('last_stop_time'):
            return self._engine.last_stop_time
        else:
            return "Unknown"


class EngineClient:

    def __init__(self, channel):
        self._stub = EngineDataStub(channel)

    def get_data(self, engine_instance):
        request = engine_request()
        request.engine_id = engine_instance
        try:
            result = self._stub.GetEngineData(request)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info("Server not accessible")
            else:
                _logger.error("GetEngineData - Error accessing server:%s" % err)
            raise GrpcAccessException
        if result.error_message == 'NO_ERROR':
            return EngineProxy(result.data)
        else:
            _logger.error(f"EngineData => No engine instance #{engine_instance}")
            return None


class NavigationDataServerProxy:

    def __init__(self, address):
        self._address = address
        self._channel = grpc.insecure_channel(address)

    @property
    def channel(self):
        return self._channel




