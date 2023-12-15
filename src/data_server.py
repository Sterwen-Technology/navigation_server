#-------------------------------------------------------------------------------
# Name:        data_server
# Purpose:      The data server decodes and manage the current set of navigation
#               And more generally the ship data
# Author:      Laurent Carré
#
# Created:     01/08/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import os
import logging
from argparse import ArgumentParser
from concurrent import futures
import grpc
import signal
import time
from generated.input_server_pb2_grpc import NMEAInputServerServicer, add_NMEAInputServerServicer_to_server
from generated.nmea_messages_pb2 import server_resp
from nmea2000.nmea2k_manufacturers import Manufacturers
from nmea2000.nmea2k_pgndefs import PGNDefinitions
from nmea_data.nmea_statistics import N2KStatistics, NMEA183Statistics
from nmea_data.data_configuration import NavigationDataConfiguration
from utilities.log_utilities import NavigationLogSystem
from utilities.global_variables import MessageServerGlobals
from nmea2000.nmea2k_decode_dispatch import get_n2k_object_from_protobuf

_version = "V0.1"


def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument('-s', '--settings', action='store', type=str, default='./conf/data-structure.yml')
    p.add_argument('-d', '--working_dir', action='store', type=str)
    p.add_argument('-p', '--port', action="store", type=int, default=4504)

    return p


parser = _parser()
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"
_logger = logging.getLogger("ShipDataServer")


class Options(object):
    def __init__(self, p):
        self.parser = p
        self.options = None

    def __getattr__(self, name):
        if self.options is None:
            self.options = self.parser.parse_args()
        try:
            return getattr(self.options, name)
        except AttributeError:
            raise AttributeError(name)


class DataServicer(NMEAInputServerServicer):

    def __init__(self, dataset):
        self._dataset = dataset

    def pushNMEA(self, request, context):
        resp = server_resp()
        resp.reportCode = 0
        if request.HasField("N2K_msg"):
            msg = request.N2K_msg
            self._dataset.add_n2kentry(msg.pgn, msg.sa)
        elif request.HasField("N0183_msg"):
            msg = request.N0183_msg
            self._dataset.add_n183entry(msg.talker, msg.formatter)
        else:
            _logger.error("pushNMEA unknown type of message")
        return resp

    def pushDecodedNMEA2K(self, request, context):
        resp = server_resp()
        resp.reportCode = 0
        try:
            n2k_object = get_n2k_object_from_protobuf(request)
        except Exception as e:
            resp.reportCode = 1
            resp.status = str(e)
            return resp
        print(n2k_object)
        return resp

    def status(self, request, context):
        resp = server_resp()
        resp.reportCode = 0
        resp.status = "OK"
        print("######################## New Session from client###############################")
        return resp


class GrpcServer:

    def __init__(self, opts, data_set):
        port = opts.port
        address = "0.0.0.0:%d" % port
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        add_NMEAInputServerServicer_to_server(DataServicer(data_set), self._server)
        self._server.add_insecure_port(address)
        _logger.info("Data server ready on address:%s" % address)

    def start(self):
        self._server.start()
        _logger.info("Data server started")

    def wait(self):
        self._server.wait_for_termination()

    def stop(self):
        self._server.stop(0.1)


class DataStatistics:

    def __init__(self):
        self._n2kstats = N2KStatistics()
        self._n183stats = NMEA183Statistics()
        self._server = None
        self._sigtime = 0
        signal.signal(signal.SIGINT, self.handler)

    def handler(self, signum, frame):
        t = time.monotonic()
        if t - self._sigtime > 10.0:
            self._sigtime = t
            self._n2kstats.print_entries()
            self._n183stats.print_entries()
        else:
            self._server.stop()

    def set_server(self, server):
        self._server = server

    def add_n2kentry(self, pgn, sa):
        self._n2kstats.add_entry(pgn, sa)

    def add_n183entry(self, talker, formatter):
        self._n183stats.add_entry(talker, formatter)


def main():

    opts = parser.parse_args()
    if opts.working_dir is not None:
        os.chdir(opts.working_dir)
    else:
        if os.getcwd() != default_base_dir:
            os.chdir(default_base_dir)
    NavigationLogSystem.create_log("Starting Data server version %s - copyright Sterwen Technology 2021-2023" % _version)
    config = NavigationDataConfiguration(opts.settings)
    NavigationLogSystem.finalize_log(config)
    _logger.info("Navigation data server working directory:%s" % os.getcwd())
    MessageServerGlobals.manufacturers = Manufacturers('./def/Manufacturers.N2kDfn.xml')
    MessageServerGlobals.pgn_definitions = PGNDefinitions('./def/PGNDefns.N2kDfn.xml')
    stats = DataStatistics()
    grpc_server = GrpcServer(opts, stats)
    stats.set_server(grpc_server)
    grpc_server.start()
    grpc_server.wait()


if __name__ == '__main__':
    main()
