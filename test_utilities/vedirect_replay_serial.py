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


import sys,os
import time
import serial

from argparse import ArgumentParser


def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument("-o", "--output", action="store", type=str,
         help="Serial port for the VEdirect Output")
    p.add_argument("-b", "--baudrate", action="store", type=int,
        default=19200,
        help="Baud rate for the VEDirect output, usually 19200, which is also the default")
    p.add_argument('-f', '--file', action='store', default=None, help='File for input')
    p.add_argument('-s','--sleep', action='store', type=float, default=0.25)
    p.add_argument('-c', '--count', action='store', type=int, default=0)

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

    if opts.file is None:
        print("File argument missing")
        return
    else:
        try:
            fd = open(opts.file,'rb')
        except IOError as e:
            print(e)
            return
        sock = None
        print("Reading VEDirect in file:", opts.file)

    print("Opening serial output %s" % opts.output)
    try:
        output = serial.Serial(port=opts.output, baudrate=opts.baudrate)
    except IOError as e:
        print(e)
        return
    line_count = 0
    while True:

        try:
            msg = fd.readline()
            if len(msg) == 0:
                break
            data_idx = msg.find(b'>')
            if data_idx == -1:
                continue
            data = bytearray.fromhex(msg[data_idx+1:].decode())
            print(data)
            if len(data) == 0:
                break
            output.write(data)
            line_count += 1
            if 0 < opts.count <= line_count:
                break
        except KeyboardInterrupt:
            break

    output.close()
    if sock is not None:
        sock.close()


if __name__ == '__main__':
    main()
