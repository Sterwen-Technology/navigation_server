#-------------------------------------------------------------------------------
# Name:        navigation_date_client
# Purpose:     proxy to access the various navigation services
#
# Author:      Laurent Carré
#
# Created:     17/07/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.generated.navigation_data_pb2 import *
from navigation_server.generated.navigation_data_pb2_grpc import *

from navigation_server.router_common import pb_enum_string, ProtobufProxy, GrpcAccessException

_logger = logging.getLogger("ShipDataClient." + __name__)


class EngineProxy(ProtobufProxy):

    def __init__(self, engine_msg: engine_data):
        self._msg = engine_msg

    @property
    def state(self):
        return pb_enum_string(self._msg, 'state', self._msg.state)

    @property
    def last_start_time(self):
        if self._engine.HasField('last_start_time'):
            return self._msg.last_start_time
        else:
            return "Unknown"

    @property
    def last_stop_time(self):
        if self._engine.HasField('last_stop_time'):
            return self._msg.last_stop_time
        else:
            return "Unknown"


class EngineEventProxy(ProtobufProxy):

    @property
    def current_state(self):
        return pb_enum_string(self._msg, 'current_state', self._msg.current_state)

    @property
    def previous_state(self):
        return pb_enum_string(self._msg, 'previous_state', self._msg.previous_state)


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
                _logger.error("GetEngineData - Server not accessible")
            else:
                _logger.error("GetEngineData - Error accessing server:%s" % err)
            raise GrpcAccessException
        if result.error_message == 'NO_ERROR':
            return EngineProxy(result.data)
        else:
            _logger.error(f"EngineData => No engine instance #{engine_instance}")
            return None

    def get_events(self, engine_instance):
        request = engine_request()
        request.engine_id = engine_instance
        try:
            result = self._stub.GetEngineEvents(request)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("GetEngineEvents - Server not accessible:%s" % err)
            else:
                _logger.error("GetEngineEvents - Error accessing server:%s" % err)
            raise GrpcAccessException
        if result.error_message == 'NO_ERROR':
            events = []
            for e_pb in result.events:
                events.append(EngineEventProxy(e_pb))
            return events
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




