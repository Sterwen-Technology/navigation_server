# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

import generated.navigation_data_pb2 as navigation__data__pb2



class EngineDataStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.GetEngineData = channel.unary_unary(
                '/EngineData/GetEngineData',
                request_serializer=navigation__data__pb2.engine_request.SerializeToString,
                response_deserializer=navigation__data__pb2.engine_response.FromString,
                )
        self.GetEngineEvents = channel.unary_unary(
                '/EngineData/GetEngineEvents',
                request_serializer=navigation__data__pb2.engine_request.SerializeToString,
                response_deserializer=navigation__data__pb2.engine_response.FromString,
                )


class EngineDataServicer(object):
    """Missing associated documentation comment in .proto file."""

    def GetEngineData(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def GetEngineEvents(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_EngineDataServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'GetEngineData': grpc.unary_unary_rpc_method_handler(
                    servicer.GetEngineData,
                    request_deserializer=navigation__data__pb2.engine_request.FromString,
                    response_serializer=navigation__data__pb2.engine_response.SerializeToString,
            ),
            'GetEngineEvents': grpc.unary_unary_rpc_method_handler(
                    servicer.GetEngineEvents,
                    request_deserializer=navigation__data__pb2.engine_request.FromString,
                    response_serializer=navigation__data__pb2.engine_response.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'EngineData', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class EngineData(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def GetEngineData(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/EngineData/GetEngineData',
            navigation__data__pb2.engine_request.SerializeToString,
            navigation__data__pb2.engine_response.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def GetEngineEvents(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/EngineData/GetEngineEvents',
            navigation__data__pb2.engine_request.SerializeToString,
            navigation__data__pb2.engine_response.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)
