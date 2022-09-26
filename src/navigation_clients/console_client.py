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

import grpc

from utilities.protobuf_utilities import *

from generated.console_pb2 import *
from generated.console_pb2_grpc import *

_logger = logging.getLogger("ShipDataClient")


class ConsoleAccessException(Exception):
    pass


class ProtobufProxy:
    '''
    Abstract class to encapsulate access to protobuf message elements
    '''

    def __init__(self, msg):
        self._msg = msg

    def __getattr__(self, item):
        try:
            return getattr(self._msg, item)
        except AttributeError:
            raise AttributeError(item)


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

    def sub_servers(self) -> SubServerProxy:
        for s in self._sub_servers:
            yield s

    def get_sub_servers(self):
        return self._sub_servers


class ConsoleClient:

    def __init__(self, address):
        self._channel = grpc.insecure_channel(address)
        self._stub = NavigationConsoleStub(self._channel)
        self._address = address
        self._req_id = 0
        _logger.info("Console on navigation server %s" % address)

    def get_couplers(self):
        couplers = []
        req = Request(id=self._req_id)
        self._req_id += 1
        try:
            for inst in self._stub.GetCouplers(req):
                couplers.append(CouplerProxy(inst))
            return couplers
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info("Server not accessible")
            else:
                _logger.error("Get Couplers - Error accessing server:%s" % err)
            raise ConsoleAccessException

    def get_coupler(self, coupler_name):
        req = Request(id=self._req_id, target=coupler_name)
        self._req_id += 1
        try:
            inst = self._stub.GetCoupler(req)
            return CouplerProxy(inst)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info("Server not accessible")
            else:
                _logger.error("Get Coupler - Error accessing server:%s" % err)
            raise ConsoleAccessException

    def send_cmd(self, target, command):
        req = Request(id=self._req_id, target=target, cmd=command)
        self._req_id += 1
        try:
            resp = self._stub.CouplerCmd(req)
            return resp
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info("Server not accessible")
            else:
                _logger.error("Send Cmd - Error accessing server:%s" % err)
            raise ConsoleAccessException

    def server_status(self):
        req = Request(id=self._req_id)
        self._req_id += 1
        try:
            server_msg = self._stub.ServerStatus(req)
            return ServerProxy(server_msg)
        except grpc.RpcError as err:
            # print(err.code(), err.details())
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.info("Server not accessible")
            raise ConsoleAccessException

    def server_cmd(self, cmd, target=None):
        req = Request(id=self._req_id)
        self._req_id += 1
        req.cmd = cmd
        if target is not None:
            req.target = target
        try:
            response = self._stub.ServerCmd(req)
            _logger.info('Server Response status %s' % response.status)
            return response.status
        except grpc.RpcError as err:

            # print(err.code(), err.details())
            if cmd == 'stop' and err.details().startswith('GOAWAY'):
                _logger.debug("Server Cmd - Error accessing server:%s" % err)
                return
            else:
                _logger.error("Server Cmd - Error accessing server:%s" % err)
            raise ConsoleAccessException


