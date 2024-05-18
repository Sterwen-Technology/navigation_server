#-------------------------------------------------------------------------------
# Name:        Console
# Purpose:     Console interface for navigation server
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
from collections import namedtuple
from generated.console_pb2 import *
from generated.console_pb2_grpc import *
from socket import gethostname
from google.protobuf.json_format import MessageToJson


from nmea_routing.configuration import NavigationConfiguration
from nmea_routing.server_common import NavigationServer
from nmea_routing.grpc_server_service import GrpcService
# from nmea2000.nmea2k_controller import NMEA2000Device
from utilities.protob_arguments import *

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class ConsoleServicer(NavigationConsoleServicer):

    def __init__(self, console):
        self._console = console

    @staticmethod
    def coupler_resp(i):
        resp = CouplerMsg()
        resp.name = i.object_name()
        resp.coupler_class = type(i).__name__
        if i.is_alive():
            if i.is_suspended():
                resp.state = State.SUSPENDED
            else:
                resp.state = State.RUNNING
        else:
            resp.state = State.STOPPED
        state = i.state()
        if 0 < state > 3:
            _logger.error("Coupler %s wrong device state %d must in range 0-3" % (resp.name, state))
            raise ValueError
        resp.dev_state = i.state()
        resp.protocol = i.protocol()
        resp.msg_in = i.total_input_msg()
        resp.msg_raw = i.total_msg_raw()
        resp.msg_out = i.total_output_msg()
        resp.input_rate = i.input_rate()
        resp.input_rate_raw = i.input_rate_raw()
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
        _logger.debug("Console GetCouplers (nb=%d)" % len(self._console.couplers()))
        for i in self._console.couplers():
            resp = self.coupler_resp(i)
            _logger.debug("Console GetCouplers sending coupler %s" % i.object_name())
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
            func = getattr(coupler, cmd)
        except AttributeError:
            resp.status = "Command %s not found" % cmd
            return resp
        if request.HasField('kwargs'):
            _logger.debug("Command %s sent with arguments" % cmd)
            args = protob_to_dict(request.kwargs.arguments)
            result = func(args)
        else:
            result = func()
        if type(result) == dict and len(result) > 0:
            _logger.debug("Command %s with result dict %s" % (cmd, result))
            dict_to_protob(result, resp.response_values)

        resp.status = " SUCCESS"
        return resp

    def ServerStatus(self, request, context):
        _logger.debug("Console server status ")
        resp = NavigationServerMsg(id=request.id)
        server = self._console.main_server()
        resp.name = server.name
        resp.version = server.version()
        resp.start_time = server.start_time_str()
        resp.state = State.RUNNING
        resp.hostname = gethostname()
        for sr in self._console.get_servers():
            _logger.debug("server record %s" % sr.name)
            sub_serv = Server()
            sub_serv.server_class = sr.class_name
            sub_serv.name = sr.name
            sub_serv.server_type = sr.server.server_type()
            sub_serv.port = sr.server.port
            sub_serv.protocol = sr.server.protocol()
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
            try:
                resp.status = server.start_coupler(i_name)
            except Exception as err:
                _logger.error("ServerCmd start_coupler execution error:%s" % err)
                resp.status = f'ServerCmd execution error:{err}'
        else:
            resp.status = f'unknown command {request.cmd}'
        _logger.debug("ServerCmd response %s" % resp.status)
        return resp

    def GetServerDetails(self, request, context):
        '''
        Warning not yet implemented
        '''
        _logger.debug("Get Server %s details" % request.target)
        resp = Response(id=request.id)
        try:
            server = self._console.get_server(request.target)
        except KeyError:
            resp.status = "Server %s not found" % request.target
            return resp
        resp.status = server.get_details()
        return resp

    def GetDevices(self, request, context):
        _logger.debug("Get NMEA200 devices request")
        n2k_svr = self._console.get_server_by_type('NMEA2KController')
        if n2k_svr is None:
            _logger.debug("No NMEA200 Server present")
            return
        for device in n2k_svr.get_device():
            resp = N2KDeviceMsg()
            resp.address = device.address
            resp.changed = device.changed()
            device.clear_change_flag()
            _logger.debug("Console sending NMEA2000 Device address %d info" % device.address)
            if device.iso_name is not None:
                device.iso_name.set_protobuf(resp.iso_name)
                resp.iso_name.manufacturer_name = device.manufacturer_name
            else:
                _logger.debug("Device address %d partial info only" % device.address)
            resp.last_time_seen = device.last_time_seen
            if device.product_information is not None:
                device.product_information.set_protobuf(resp.product_information)
            if device.configuration_information is not None:
                device.configuration_information.set_protobuf(resp.configuration_information)
            yield resp
        _logger.debug("Get NMEA Devices END")
        return


ServerRecord = namedtuple('ServerRecord', ['server', 'name', 'class_name'])


class Console(GrpcService):

    def __init__(self, options):
        super().__init__(options)
        self._servers = {}
        self._couplers = {}
        self._injectors = {}

    def finalize(self):
        super().finalize()
        add_NavigationConsoleServicer_to_server(ConsoleServicer(self), self.grpc_server)

    def add_server(self, server):
        record = ServerRecord(server, server.name, server.class_name())
        self._servers[server.name] = record

    def get_servers(self) -> ServerRecord:
        for sr in self._servers.values():
            if sr.class_name not in ('Console', 'NavigationMainServer'):
                yield sr

    def get_server_by_type(self, server_type: str) -> NavigationServer:
        server_class = NavigationConfiguration.get_conf().get_class(server_type)
        for sr in self._servers.values():
            if issubclass(sr.server.__class__, server_class):
                return sr.server
        return None

    def get_server(self, name):
        return self._servers[name].server

    def add_coupler(self, coupler):
        # print("Console add coupler:", coupler.object_name())
        self._couplers[coupler.object_name()] = coupler

    def couplers(self):
        return self._couplers.values()

    def coupler(self, name):
        return self._couplers[name]

    def main_server(self):
        return self._servers['main'].server

