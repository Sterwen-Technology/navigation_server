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

from collections import namedtuple
from concurrent import futures
from generated.console_pb2 import *
from generated.console_pb2_grpc import *

from nmea_routing.server_common import *

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class ConsoleServicer(NavigationConsoleServicer):

    def __init__(self, console):
        self._console = console

    @staticmethod
    def coupler_resp(i):
        resp = CouplerMsg()
        resp.name = i.name()
        resp.coupler_class = type(i).__name__
        if i.is_alive():
            resp.state = State.RUNNING
        else:
            resp.state = State.STOPPED
        resp.dev_state = i.state()
        resp.protocol = i.protocol()
        resp.msg_in = i.total_input_msg()
        resp.msg_out = i.total_output_msg()
        resp.input_rate = i.input_rate()
        resp.output_rate = i.output_rate()
        return resp

    def GetCoupler(self, request, context):
        _logger.debug("Console GetCoupler name %s" % request.target)
        try:
            i = self._console.coupler(request.target)
            resp = self.coupler_resp(i)
        except KeyError:
            _logger.error("Console access to non existent coupler %s" % request.target)
            resp = CouplerMsg(status="Coupler not found")
        return resp

    def GetCouplers(self, request, context):
        _logger.debug("Console GetCouplers")
        for i in self._console.couplers():
            resp = self.coupler_resp(i)
            _logger.debug("Console GetCouplers sending coupler %s" % i.name())
            yield resp
        return

    def CouplerCmd(self, request, context):
        resp = Response()
        resp.id = request.id
        _logger.debug("Coupler cmd %s %s" % (request.target, request.cmd))
        try:
            coupler = self._console.coupler(request.target)
        except KeyError:
            resp.status = "Coupler %s not found" % request.target
            _logger.error("Console coupler cmd target not found: %s" % request.target)
            return resp
        cmd = request.cmd
        try:
            ret_val = getattr(coupler, cmd)()
        except AttributeError:
            resp.status = "Command %s not found" % cmd
            return resp
        resp.status = " SUCCESS value=%s" % ret_val
        return resp

    def ServerStatus(self, request, context):
        _logger.debug("Console server status ")
        resp = NavigationServerMsg(id=request.id)
        server = self._console.main_server()
        resp.name = server.name()
        resp.version = server.version()
        resp.start_time = server.start_time_str()
        resp.state = State.RUNNING
        for sr in self._console.get_servers():
            _logger.debug("server record %s" % sr.name)
            sub_serv = Server()
            sub_serv.server_class = sr.class_name
            sub_serv.name = sr.name
            sub_serv.server_type = sr.server.server_type()
            sub_serv.port = sr.server.port
            sub_serv.running = sr.server.running()
            if sr.server.running():
                sub_serv.nb_connections = sr.server.nb_connections()
                _logger.debug("%s nb_connections %d" % (sr.name, sub_serv.nb_connections))
                if sub_serv.nb_connections > 0:
                    conn = Connection()
                    for src in sr.server.connections():
                        _logger.debug("Connection %s %d %d" % (src.address, src.port, src.msg_count))
                        conn.remote_ip = src.address
                        conn.remote_port = src.port
                        conn.total_msg = src.msg_count
                    sub_serv.connections.append(conn)
            resp.servers.append(sub_serv)
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


ServerRecord = namedtuple('ServerRecord', ['server', 'name', 'class_name'])


class Console(NavigationServer):

    def __init__(self, options):
        super().__init__(options)
        self._servers = {}
        self._couplers = {}
        self._injectors = {}
        self._connection = None
        self._end_event = None
        address = "0.0.0.0:%d" % self._port
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        add_NavigationConsoleServicer_to_server(ConsoleServicer(self), self._grpc_server)
        self._grpc_server.add_insecure_port(address)

    def add_server(self, server):
        record = ServerRecord(server, server.name(), server.class_name())
        self._servers[server.name()] = record

    def get_servers(self) -> ServerRecord:
        for sr in self._servers.values():
            if sr.class_name not in ('Console', 'NavigationMainServer'):
                yield sr

    def add_coupler(self, coupler):
        self._couplers[coupler.name()] = coupler

    def couplers(self):
        return self._couplers.values()

    def coupler(self, name):
        return self._couplers[name]

    def main_server(self):
        return self._servers['main'].server

    def start(self) -> None:
        _logger.info("Console starting on port %d" % self._port)
        self._grpc_server.start()

    def stop(self):
        _logger.info("Stopping Console GRPC Server")
        self._end_event = self._grpc_server.stop(0.1)

    def join(self):
        if self._end_event is not None:
            self._end_event.wait()
