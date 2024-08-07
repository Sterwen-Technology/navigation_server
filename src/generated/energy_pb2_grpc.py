# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

import generated.energy_pb2 as energy__pb2



class solar_mpptStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.GetDeviceInfo = channel.unary_unary(
                '/solar_mppt/GetDeviceInfo',
                request_serializer=energy__pb2.request.SerializeToString,
                response_deserializer=energy__pb2.MPPT_device.FromString,
                )
        self.GetOutput = channel.unary_unary(
                '/solar_mppt/GetOutput',
                request_serializer=energy__pb2.request.SerializeToString,
                response_deserializer=energy__pb2.solar_output.FromString,
                )


class solar_mpptServicer(object):
    """Missing associated documentation comment in .proto file."""

    def GetDeviceInfo(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def GetOutput(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_solar_mpptServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'GetDeviceInfo': grpc.unary_unary_rpc_method_handler(
                    servicer.GetDeviceInfo,
                    request_deserializer=energy__pb2.request.FromString,
                    response_serializer=energy__pb2.MPPT_device.SerializeToString,
            ),
            'GetOutput': grpc.unary_unary_rpc_method_handler(
                    servicer.GetOutput,
                    request_deserializer=energy__pb2.request.FromString,
                    response_serializer=energy__pb2.solar_output.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'solar_mppt', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class solar_mppt(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def GetDeviceInfo(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/solar_mppt/GetDeviceInfo',
            energy__pb2.request.SerializeToString,
            energy__pb2.MPPT_device.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def GetOutput(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/solar_mppt/GetOutput',
            energy__pb2.request.SerializeToString,
            energy__pb2.solar_output.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)
