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

from concurrent import futures
from generated.console_pb2 import *
from generated.console_pb2_grpc import *

from nmea_routing.server_common import *

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class ConsoleServicer(NavigationConsoleServicer):

    def __init__(self, console):
        self._console = console

    @staticmethod
    def instrument_resp(i):
        resp = InstrumentMsg()
        resp.name = i.name()
        resp.instrument_class = type(i).__name__
        if i.is_alive():
            resp.state = State.RUNNING
        else:
            resp.state = State.STOPPED
        resp.dev_state = i.state()
        resp.protocol = i.protocol()
        resp.msg_in = i.total_input_msg()
        resp.msg_out = i.total_output_msg()
        return resp

    def GetInstrument(self, request, context):
        _logger.debug("Console GetInstrument name %s" % request.target)
        try:
            i = self._console.coupler(request.target)
            resp = self.instrument_resp(i)
        except KeyError:
            _logger.error("Console access to non existent coupler %s" % request.target)
            resp = InstrumentMsg(status="Coupler not found")
        return resp

    def GetInstruments(self, request, context):
        _logger.debug("Console GetInstruments")
        for i in self._console.couplers():
            resp = self.instrument_resp(i)
            _logger.debug("Console GetInstruments sending coupler %s" % i.name())
            yield resp
        return

    def InstrumentCmd(self, request, context):
        resp = Response()
        resp.id = request.id
        try:
            instrument = self._console.coupler(request.target)
        except KeyError:
            resp.status = "Coupler %s not found" % request.target
            return resp
        cmd = request.cmd
        try:
            ret_val = getattr(instrument, cmd)()
        except AttributeError:
            resp.status = "Command %s not found" % cmd
            return resp
        resp.status = " SUCCESS value=%s" % ret_val
        return resp

    def ServerStatus(self, request, context):
        _logger.debug("Console server status ")
        resp = ServerMsg(id=request.id)
        server = self._console.main_server()
        resp.name = server.name()
        resp.state = State.RUNNING
        return resp

    def ServerCmd(self, request, context):
        _logger.debug("Console server cmd %s" % request.cmd)
        resp = Response(id=request.id)
        server = self._console.main_server()
        if request.cmd == "stop":
            server.request_stop(0)
            resp.status = "stop requested"
        elif request.cmd == "start_coupler":
            i_name = request.target
            resp.status = server.start_coupler(i_name)
        _logger.debug("ServerCmd response %s" % resp.status)
        return resp


class Console(NavigationServer):

    def __init__(self, options):
        super().__init__(options)
        self._servers = {}
        self._couplers = {}
        self._injectors = {}
        self._connection = None
        self._end_event = None
        address = "0.0.0.0:%d" % self._port
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_NavigationConsoleServicer_to_server(ConsoleServicer(self), self._grpc_server)
        self._grpc_server.add_insecure_port(address)

    def add_server(self, server):
        self._servers[server.name()] = server

    def add_coupler(self, coupler):
        self._couplers[coupler.name()] = coupler

    def couplers(self):
        return self._couplers.values()

    def coupler(self, name):
        return self._couplers[name]

    def main_server(self):
        return self._servers['main']

    def start(self) -> None:
        _logger.info("Console starting on port %d" % self._port)
        self._grpc_server.start()

    def stop(self):
        _logger.info("Stopping Console GRPC Server")
        self._end_event = self._grpc_server.stop(0.1)

    def join(self):
        if self._end_event is not None:
            self._end_event.wait()
