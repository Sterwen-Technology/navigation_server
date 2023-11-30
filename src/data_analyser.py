#-------------------------------------------------------------------------------
# Name:        data_analyser
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     23/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import logging
from argparse import ArgumentParser
from concurrent import futures
import grpc
import signal
import time
import os
from generated.input_server_pb2_grpc import NMEAInputServerServicer, add_NMEAInputServerServicer_to_server
from generated.nmea_messages_pb2 import server_resp
from nmea2000.nmea2k_manufacturers import Manufacturers
from nmea2000.nmea2k_pgndefs import PGNDefinitions
from nmea_data.nmea_statistics import N2KStatistics, NMEA183Statistics
from nmea2000.nmea2000_msg import NMEA2000Msg
from utilities.global_variables import MessageServerGlobals

_version = "V1.00"


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-d', '--directory', action='store', type=str, default='/mnt/meaban/Bateau/tests')
    p.add_argument('-p', '--port', action="store", type=int, default=4504)
    p.add_argument('-sim', '--simulator', action="store")

    return p


parser = _parser()
_logger = logging.getLogger("Data_analyser")


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
            n2k_msg = NMEA2000Msg(msg.pgn, protobuf=msg)
            # print(n2k_msg.format2())
            self._dataset.add_n2kentry(n2k_msg)
        elif request.HasField("N0183_msg"):
            msg = request.N0183_msg
            self._dataset.add_n183entry(msg.talker, msg.formatter)
        else:
            _logger.error("pushNMEA unknown type of message")
        return resp

    def status(self, request, context):
        resp = server_resp()
        resp.reportCode = 0
        resp.status = "OK"
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

    def __init__(self, file):
        self._n2kstats = N2KStatistics()
        self._n183stats = NMEA183Statistics()
        self._server = None
        self._sigtime = 0
        self._file = file
        signal.signal(signal.SIGINT, self.handler)

    def handler(self, signum, frame):
        t = time.monotonic()
        if t - self._sigtime > 10.0:
            self._sigtime = t
            self._n2kstats.print_entries()
            self._n2kstats.write_entries(self._file)
            self._n183stats.print_entries()
        else:
            self._server.stop()

    def set_server(self, server):
        self._server = server

    def add_n2kentry(self, msg):
        self._n2kstats.add_entry(msg)

    def add_n183entry(self, talker, formatter):
        self._n183stats.add_entry(talker, formatter)


def main():

    opts = parser.parse_args()
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(logging.INFO)
    output_file = os.path.join(opts.directory, 'pgn.csv')

    MessageServerGlobals.manufacturers = Manufacturers('./def/Manufacturers.N2kDfn.xml')
    MessageServerGlobals.pgn_definitions = PGNDefinitions('./def/PGNDefns.N2kDfn.xml')
    stats = DataStatistics(output_file)
    grpc_server = GrpcServer(opts, stats)
    stats.set_server(grpc_server)
    grpc_server.start()
    grpc_server.wait()


if __name__ == '__main__':
    main()
