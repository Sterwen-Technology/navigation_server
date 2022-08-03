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

from generated.console_pb2 import *
from generated.console_pb2_grpc import *

_logger = logging.getLogger("ShipDataClient")


class InstrumentProxy:

    def __init__(self, msg: InstrumentMsg):
        self._msg = msg

    @property
    def name(self):
        return self._msg.name

    @property
    def state(self):
        return self._msg.DESCRIPTOR.fields_by_name['state'].enum_type.values_by_number[self._msg.state].name

    @property
    def dev_state(self):
        return self._msg.DESCRIPTOR.fields_by_name['dev_state'].enum_type.values_by_number[self._msg.dev_state].name

    @property
    def protocol(self):
        return self._msg.protocol

    @property
    def msg_in(self):
        return self._msg.msg_in

    @property
    def msg_out(self):
        return self._msg.msg_out

    def stop(self, client):
        return client.send_cmd(self._msg.name, 'stop')

    def start(self, client):
        return client.server_cmd('start_coupler', self._msg.name)


class ServerProxy:

    def __init__(self, msg):
        self._msg = msg

    @property
    def name(self):
        return self._msg.name

    @property
    def version(self):
        return self._msg.version

    @property
    def state(self):
        return self._msg.DESCRIPTOR.fields_by_name['state'].enum_type.values_by_number[self._msg.state].name


class ConsoleClient:

    def __init__(self, address):
        self._channel = grpc.insecure_channel(address)
        self._stub = NavigationConsoleStub(self._channel)
        self._req_id = 0
        _logger.info("Console on navigation server %s" % address)

    def get_instruments(self):
        instruments = []
        req = Request(id=self._req_id)
        self._req_id += 1
        try:
            for inst in self._stub.GetInstruments(req):
                instruments.append(InstrumentProxy(inst))
            return instruments
        except Exception as err:
            _logger.error("Error accessing server:%s" % err)
            return None

    def get_instrument(self, inst_name):
        req = Request(id=self._req_id, target=inst_name)
        self._req_id += 1
        try:
            inst = self._stub.GetInstrument(req)
            return InstrumentProxy(inst)
        except Exception as err:
            _logger.error("Error accessing server:%s" % err)
            return None

    def send_cmd(self, target, command):
        req = Request(id=self._req_id, target=target, cmd=command)
        self._req_id += 1
        try:
            resp = self._stub.InstrumentCmd(req)
            return resp
        except Exception as err:
            _logger.error("Error accessing server:%s" % err)
            return None

    def server_status(self):
        req = Request(id=self._req_id)
        self._req_id += 1
        try:
            server_msg = self._stub.ServerStatus(req)
            return ServerProxy(server_msg)
        except Exception as err:
            _logger.error("Error accessing server:%s" % err)
            return None

    def server_cmd(self, cmd, target=None):
        req = Request(id=self._req_id)
        self._req_id += 1
        req.cmd = cmd
        if target is not None:
            req.target = target
        try:
            response = self._stub.ServerCmd(req)
            _logger.info('Response status %s' % response.status)
            return response.status
        except Exception as err:
            _logger.error("Error accessing server:%s" % err)
            return None


