#-------------------------------------------------------------------------------
# Name:        Console
# Purpose:     Console interface for navigation server
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import grpc
from concurrent import futures
from console_pb2 import *
from console_pb2_grpc import *

from server_common import *

_logger = logging.getLogger("ShipDataServer")


class ConsoleServicer(NavigationConsoleServicer):

    def __init__(self, console):
        self._console = console

    def GetInstruments(self, request, context):
        _logger.debug("Console GetInstruments")
        for i in self._console.instruments():
            resp = InstrumentMsg()
            resp.name = i.name()
            resp.instrument_class = type(i).__name__
            if i.is_alive():
                resp.state = InstrumentMsg.RUNNING
            else:
                resp.state = InstrumentMsg.STOPPED
            resp.dev_state = i.state()
            resp.protocol = i.protocol()
            resp.msg_in = i.total_input_msg()
            resp.msg_out = i.total_output_msg()
            _logger.debug("Console GetInstruments sending instrument %s" % i.name())
            yield resp
        return

    def InstrumentCmd(self, request, context):
        resp = Response()
        resp.id = request.id
        try:
            instrument = self._console.instrument(request.target)
        except KeyError:
            resp.status = "Instrument %s not found" % request.target
            return resp
        cmd = request.cmd
        try:
            ret_val = getattr(instrument, cmd)()
        except AttributeError:
            resp.status = "Command %s not found" % cmd
            return resp
        resp.status = " SUCCESS value=%s" % ret_val
        return resp


class Console(NavigationServer):

    def __init__(self, options):
        super().__init__(options)
        self._servers = {}
        self._instruments = {}
        self._injectors = {}
        self._connection = None
        address = "0.0.0.0:%d" % self._port
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_NavigationConsoleServicer_to_server(ConsoleServicer(self), self._grpc_server)
        self._grpc_server.add_insecure_port(address)

    def add_server(self, server):
        self._servers[server.name()] = server

    def add_instrument(self, instrument):
        self._instruments[instrument.name()] = instrument

    def instruments(self):
        return self._instruments.values()

    def instrument(self, name):
        return self._instruments[name]

    def start(self) -> None:
        _logger.info("Console starting on port %d" % self._port)
        self._grpc_server.start()

    def stop(self):
        _logger.info("Stopping Console GRPC Server")
        self._end_event = self._grpc_server.stop(0.1)

    def join(self):
        self._end_event.wait()
