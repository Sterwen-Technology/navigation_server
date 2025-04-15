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


import sys
import serial

from argparse import ArgumentParser


def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument("-i", "--interface", action="store", type=str,
        default='/dev/ttyUSB1', help="Serial port for the NMEA Input")
    p.add_argument("-b", "--baudrate", action="store", type=int,
        default=38400,
        help="Baud rate for the NMEA output, usually 4800, which is also the default")

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
    print("Opening serial output %s" % opts.interface)
    try:
        if_nmea = serial.Serial(port=opts.interface, baudrate=opts.baudrate)
    except IOError as e:
        print(e)
        return

    while True:

        try:
            if_nmea.write(b'ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n')
        except KeyboardInterrupt:
            break



if __name__ == '__main__':
    main()
