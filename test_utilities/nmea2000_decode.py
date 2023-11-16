#-------------------------------------------------------------------------------
# Name:        nmea2000_msg
# Purpose:     Manages all NMEA2000/J1939 messages
#
# Author:      Laurent Carré
#
# Created:     26/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------
import csv
import sys
import os
from argparse import ArgumentParser

from nmea2000.nmea2000_msg import *
from nmea2000.nmea2k_pgndefs import *
from nmea2000.nmea2k_manufacturers import Manufacturers

_logger = logging.getLogger("ShipDataServer")


def _parser():

    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-x', '--xml', action="store", type=str,
                   default="PGNDefns.N2kDfn.xml")
    p.add_argument('-o', '--csv_out', action="store", type=str)
    p.add_argument('-i', '--input', action='store', type=str)
    p.add_argument('-d', '--trace_level', action="store", type=str,
                   choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                   default="INFO",
                   help="Level of traces, default INFO")
    p.add_argument('-p', '--print', action='store', type=str,
                   default='None')
    p.add_argument("-l", "--log", action="store", type=str,
                   help="Logfile for all incoming NMEA sentences")
    p.add_argument("-t", "--trace", action="store", type=str)
    p.add_argument('-f', '--filter', action='store', type=str)
    p.add_argument('-of', '--output_file', action='store', type=str)
    p.add_argument('-c', '--count', action='store', type=int, default=0)
    return p


def decode_trace(line, pgn_active):
    sep_index = line.index('>')
    # print(line, sep_index, timestamp)
    if line[sep_index + 1] == '$':
        return  None
    fields = line[sep_index + 1:].split('|')
    if fields[0] != '2K':
        # print("Wrong line:%s" % line)
        return None
    pgn = int(fields[1])
    if len(pgn_active) != 0:
        if pgn not in pgn_active:
            return None
    prio = int(fields[3])
    sa = int(fields[4])
    da = int(fields[5])
    payload = bytearray.fromhex(fields[7])
    msg = NMEA2000Msg(pgn, prio, sa, da, payload)
    return msg


def file_input(filename, pgn_active, outfd=sys.stdout, max_occurence=0):
    fd = open(filename, "r")
    print(pgn_active)
    occurrence = 0
    for line in fd.readlines():
        line = line.strip('\n\r')
        # print(line)
        msg = decode_trace(line, pgn_active)
        if msg is None:
            continue
        occurrence += 1
        outfd.write(str(msg))
        outfd.write('\n')
        res = msg.decode()
        if res is not None:
            outfd.write(str(res))
            outfd.write('\n')
        outfd.flush()
        if 0 < max_occurence <= occurrence:
            break



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
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(opts.trace_level)
    if opts.xml is None:
        print("Missing XML definitions")
        return

    def_file = os.path.join("../def", opts.xml)
    print("analyzing file:", def_file)
    Manufacturers.build_manufacturers(os.path.join("../def", "Manufacturers.N2kDfn.xml"))
    defs = PGNDefinitions.build_definitions(def_file)
    if opts.print == 'ALL':
        defs.print_summary()
    if opts.csv_out is not None:
        print("Generating PGN CSV file %s" % opts.csv_out)
        fp = open(opts.csv_out, 'w')
        w = csv.writer(fp, dialect='excel')
        for pgn in defs.pgns():
            w.writerow(pgn.pgn_data())
        fp.close()
    elif opts.input is not None:
        pgn_active = []
        if opts.filter is not None:
            print(opts.filter)
            pgn_active = pgn_list(opts.filter)
        if opts.output_file is not None:
            ofd = open(opts.output_file, "w")
        else:
            ofd = sys.stdout
        file_input(opts.input, pgn_active, ofd, opts.count)


if __name__ == '__main__':
    main()