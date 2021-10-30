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
import serial
from argparse import ArgumentParser


def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument("-o", "--output", action="store", type=str,
        default='COM6', help="Serial port for the NMEA Output")
    p.add_argument("-b", "--baudrate", action="store", type=int,
        default=4800,
        help="Baud rate for the NMEA output, usually 4800, which is also the default")
    p.add_argument("-p", "--port", action="store", type=int,
                   default=3555,
                   help="Listening port for NMEA input, default is 3555")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='',
                   help="IP address or URL for NMEA Input, default is localhost")
    p.add_argument("-pr", "--protocol", action="store", type=str,
                   choices=['TCP','UDP'], default='TCP',
                   help="Protocol to read NMEA sentences, default TCP")
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


def main():
    opts = Options(parser)

    port = opts.port
    address = opts.address
    print("opening port on host %s port %d" % (address, port))
    try:
        sock = socket.create_connection((address, port))
    except OSError as e:
        print(e)
        return
    print("listening for NMEA sentences on host %s port %d" % (address, port))
    print("Opening serial output %s" % opts.output)
    try:
        output = serial.Serial(port=opts.output, baudrate=opts.baudrate)
    except IOError as e:
        print(e)
        return

    while True:
        try:
            data = sock.recv(256)
            print(data)
            if len(data) == 0:
                break
            output.write(data)
        except KeyboardInterrupt:
            break
    output.close()
    sock.close()


if __name__ == '__main__':
    main()
