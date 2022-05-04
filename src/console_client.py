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
from argparse import ArgumentParser
import sys

from console_pb2 import *
from console_pb2_grpc import *


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument("-p", "--port", action="store", type=int,
                   default=4502,
                   help="Console listening port, default 4502")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='127.0.0.1',
                   help="IP address for Navigation server, default is localhost")

    return p


parser = _parser()


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

class ConsoleClient:

    def __init__(self, address):
        self._channel = grpc.insecure_channel(address)
        self._stub = NavigationConsoleStub(self._channel)
        self._req_id = 0
        print("Console on navigation server", address)

    def get_instruments(self):
        instruments = []
        req = Request(id=self._req_id)
        try:
            for inst in self._stub.GetInstruments(req):
                instruments.append(inst)
            return instruments
        except Exception as err:
            print("Error accessing server:", err)
            return None


def main():
    opts = Options(parser)
    server = "%s:%d" % (opts.address, opts.port)
    console = ConsoleClient(server)
    result = console.get_instruments()
    if result is not None:
        for i in result:
            print(i)


if __name__ == '__main__':
    main()
