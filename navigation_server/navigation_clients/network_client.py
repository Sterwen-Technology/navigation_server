#-------------------------------------------------------------------------------
# Name:        Network client
# Purpose:     Access to gRPC Network Service
#
# Author:      Laurent Carré
#
# Created:     22/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.set_logging_root import nav_logging_root
_logger = logging.getLogger(nav_logging_root + __name__)

from navigation_server.router_common import ServiceClient, ProtobufProxy, pb_enum_string
from navigation_server.generated.network_pb2 import (NetInterface, NetParameter, DeviceType, InterfaceStatus,
                                                    NetConnection, NetworkCommand, NetworkStatus)
from navigation_server.generated.network_pb2_grpc import NetworkServiceStub



class NetConnectionProxy(ProtobufProxy):

    def __init__(self, connection:NetConnection):
        super().__init__(connection)
        self._parameters = {}
        for param in connection.parameters:
            self._parameters[param.name] = param.value

    def parameter(self, name:str) -> str:
        return self._parameters.get(name, None)

    def parameters(self) -> list[(str, str)]:
        return list(self._parameters.items())


class NetInterfaceProxy(ProtobufProxy):

    def __init__(self, interface:NetInterface):
        super().__init__(interface)
        self._connection = NetConnectionProxy(interface.conn)

    def device_type(self) -> str:
        return pb_enum_string(self._msg, 'type', self._msg.type)

    @property
    def status(self) -> str:
        return pb_enum_string(self._msg, 'status', self._msg.status)

    @property
    def connection(self) -> NetConnectionProxy:
        return self._connection

class NetworkStatusProxy(ProtobufProxy):

    def __init__(self, status:NetworkStatus):
        super().__init__(status)
        # print(status)
        self._interfaces = {}
        for interface in status.if_list:
            self._interfaces[interface.name] = NetInterfaceProxy(interface)

    def interface(self, name:str) -> NetInterfaceProxy:
        return self._interfaces.get(name, None)

    def interfaces(self) -> list[NetInterfaceProxy]:
        return list(self._interfaces.values())


class NetworkClient(ServiceClient):

    def __init__(self):
        super().__init__(NetworkServiceStub)

    def network_status(self, command:str, interface=None, connection=None):
        _logger.debug("Call network status")
        request = NetworkCommand()
        request.cmd = command
        if interface is not None:
            pass ## tbd
        if connection is not None:
            pass # tbd
        return self._server_call(self._stub.get_network_status, request, NetworkStatusProxy)

