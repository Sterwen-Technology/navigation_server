#-------------------------------------------------------------------------------
# Name:        Console Client
# Purpose:     Console client interface via GPRC for navigation server
#
# Author:      Laurent Carré
#
# Created:     04/05/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.router_common import (ProtobufProxy, pb_enum_string, dict_to_protob, protob_to_dict,
                                             ServiceClient, GrpcClient)
from navigation_server.generated.console_pb2 import CouplerMsg, Request
from navigation_server.generated.console_pb2_grpc import NavigationConsoleStub

_logger = logging.getLogger("ShipDataServer." + __name__)


class CouplerProxy(ProtobufProxy):

    def __init__(self, msg: CouplerMsg):
        super().__init__(msg)

    @property
    def state(self):
        # return self._msg.DESCRIPTOR.fields_by_name['state'].enum_type.values_by_number[self._msg.state].name
        return pb_enum_string(self._msg, 'state', self._msg.state)

    @property
    def dev_state(self):
        # return self._msg.DESCRIPTOR.fields_by_name['dev_state'].enum_type.values_by_number[self._msg.dev_state].name
        return pb_enum_string(self._msg, 'dev_state', self._msg.dev_state)

    def stop(self, client):
        return client.send_cmd(self._msg.name, 'stop')

    def start(self, client):
        return client.server_cmd('start_coupler', self._msg.name)

    def start_trace(self, client):
        return client.send_cmd(self._msg.name, 'start_trace_raw')

    def stop_trace(self, client):
        return client.send_cmd(self._msg.name, 'stop_trace')

    def suspend(self, client):
        return client.send_cmd(self._msg.name, 'suspend')

    def resume(self, client):
        return client.send_cmd(self._msg.name, 'resume')

    def send_cmd(self, client, cmd, args=None):
        return client.send_cmd(self._msg.name, cmd, args)


class SubServerProxy(ProtobufProxy):

    def __init__(self, msg):
        super().__init__(msg)


class ServerProxy(ProtobufProxy):

    def __init__(self, msg):
        super().__init__(msg)
        self._sub_servers = []
        for s in msg.servers:
            self._sub_servers.append(SubServerProxy(s))

    @property
    def state(self):
        # return self._msg.DESCRIPTOR.fields_by_name['state'].enum_type.values_by_number[self._msg.state].name
        return pb_enum_string(self._msg, 'state', self._msg.state)

    def sub_servers(self):
        for s in self._sub_servers:
            yield s

    def get_sub_servers(self):
        return self._sub_servers


class ConsoleClient(ServiceClient):


    def __init__(self):
        super().__init__(NavigationConsoleStub)

    def get_couplers(self):
        couplers = []
        req = Request()
        for coupler in self._server_call_multiple(self._stub.GetCouplers, req, CouplerProxy):
            couplers.append(coupler)
        return couplers

    def get_coupler(self, coupler_name):
        req = Request()
        req.target = coupler_name
        return self._server_call(self._stub.GetCoupler, req, CouplerProxy)


    def send_cmd(self, target, command, args=None):
        req = Request(target=target, cmd=command)
        if args is not None:
            dict_to_protob(args, req.kwargs)
        resp = self._server_call(self._stub.CouplerCmd, req,None)
        if resp.HasField('response_values'):
            return protob_to_dict(resp.response_values.arguments)
        else:
            return None

    def server_status(self):
        if self.server_state() == GrpcClient.NOT_CONNECTED:
            self._server.connect()
        req = Request()
        return self._server_call(self._stub.ServerStatus, req, ServerProxy)

    def server_cmd(self, cmd, target=None):
        req = Request()
        req.cmd = cmd
        if target is not None:
            req.target = target
        response = self._server_call(self._stub.ServerCmd, req, None)
        return response.status



