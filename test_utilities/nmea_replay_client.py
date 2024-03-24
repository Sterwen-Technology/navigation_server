#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      Laurent
#
# Created:     14/04/2019
# Copyright:   (c) Laurent 2019
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import socket
import sys,os
import time
import serial
import threading

from argparse import ArgumentParser

from router_core.server_common import NavTCPServer


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-f', '--file', action='store', default=None, help='File for input instead of server')
    p.add_argument("-p", "--port", action="store", type=int,
                   default=3555,
                   help="Listening port for NMEA input, default is 3555")

    p.add_argument("-pr", "--protocol", action="store", type=str,
                   choices=['TCP','UDP'], default='TCP')
                   help="Protocol to read NMEA sentences, default TCP")
    p.add_argument('-s','--sleep', action='store', type=float, default=0.25)

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


class Server(NavTCPServer):

    def __init__(self, opts):
        super().__init__(opts)


def main():
    opts = Options(parser)

    if opts.file is None:
        port = opts.port
        address = opts.address
        print("opening port on host %s port %d" % (address, port))
        try:
            sock = socket.create_connection((address, port))
        except OSError as e:
            print(e)
            return
        print("listening for NMEA sentences on host %s port %d" % (address, port))
    else:
        try:
            fd = open(opts.file,'rb')
        except IOError as e:
            print(e)
            return
        sock = None
        print("Reading NMEA sentence in file:", opts.file)

    print("Opening serial output %s" % opts.output)
    try:
        output = serial.Serial(port=opts.output, baudrate=opts.baudrate)
    except IOError as e:
        print(e)
        return

    while True:

        try:
            if sock is None:
                try:
                    data = fd.readline(256)
                except IOError as e:
                    print(e)
                    break
                time.sleep(opts.sleep)
            else:
                data = sock.recv(256)
            print(data)
            if len(data) == 0:
                break
            output.write(data)
        except KeyboardInterrupt:
            break

    output.close()
    if sock is not None:
        sock.close()


if __name__ == '__main__':
    main()
