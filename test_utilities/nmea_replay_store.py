#-------------------------------------------------------------------------------
# Name:        Filter replay data and store in file
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     10/04/2022
# Copyright:   (c) Sterwen-Technology Laurent Carré 2022
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import socket
import sys

from argparse import ArgumentParser

from nmea0183.nmea0183_msg import NMEA0183Filter


def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument("-o", "--output", action="store", type=str, default=None, help="File for the NMEA Output")
    p.add_argument('-f', '--filter', action='store', type=str, default=None, help='List of sentences to be collected')
    p.add_argument("-p", "--port", action="store", type=int,
                   default=3555,
                   help="Listening port for NMEA input, default is 3555")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='localhost',
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

    if opts.output is None:
        print("Output file name missing")
        return
    if opts.filter is not None:
        filter_f = NMEA0183Filter(opts.filter, ',')
    else:
        filter_f = None

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
        output = open(opts.output,"bw")
    except IOError as e:
        print(e)
        return

    while True:
        try:
            data = sock.recv(256)
            # print(data)
            if len(data) == 0:
                break
            if filter_f is None:
                output.write(data)
                print(data)
            elif filter_f.valid_sentence(data):
                output.write(data)
                print(data)
        except KeyboardInterrupt:
            break
    print("Closing connection and file")
    output.close()
    sock.close()


if __name__ == '__main__':
    main()
