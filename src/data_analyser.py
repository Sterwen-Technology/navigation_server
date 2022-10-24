#-------------------------------------------------------------------------------
# Name:        data_analyser
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     23/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import logging
from argparse import ArgumentParser
from concurrent import futures
import grpc
from generated.server_pb2_grpc import NavigationServerServicer, add_NavigationServerServicer_to_server
from generated.server_pb2 import server_resp


_version = "V1.00"


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-d', '--directory', action='store', type=str, default='/data/solidsense/navigation_data')
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


class DataServicer(NavigationServerServicer):

    def __init__(self, dataset):
        self._dataset = dataset

    def pushNMEA(self, request, context):
        resp = server_resp()
        resp.reportCode = 0
        if request.HasField("N2K_msg"):
            _logger.debug("NMEA2000 message received")
        elif request.HasField("N0183_msg"):
            _logger.debug("NMEA0183 message received")
        return resp


class GrpcServer:

    def __init__(self, opts, data_set):
        port = opts.port
        address = "0.0.0.0:%d" % port
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        add_NavigationServerServicer_to_server(DataServicer(data_set), self._server)
        self._server.add_insecure_port(address)
        _logger.info("Data server ready on address:%s" % address)

    def start(self):
        self._server.start()
        _logger.info("Data server started")

    def wait(self):
        self._server.wait_for_termination()


def main():
    opts = parser.parse_args()
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(logging.INFO)

    grpc_server = GrpcServer(opts, None)
    grpc_server.start()
    grpc_server.wait()


if __name__ == '__main__':
    main()
