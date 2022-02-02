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
from argparse import ArgumentParser
import base64

from nmea2000_msg import *
from nmea2k_pgndefs import *
from publisher import Publisher

_logger = logging.getLogger("ShipDataServer")


def _parser():

    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-x', '--xml', action="store", type=str,
                   default="PGNDefns.N2kDfn.xml")
    p.add_argument('-o', '--csv_out', action="store", type=str)
    p.add_argument('-i', '--input', action='store', type=str)
    p.add_argument('-d', '--trace_level', action="store", type=str,
                   choices=["CRITICAL","ERROR", "WARNING", "INFO", "DEBUG"],
                   default="INFO",
                   help="Level of traces, default INFO")
    p.add_argument('-p', '--print', action='store', type=str,
                   default='ALL')
    p.add_argument("-l", "--log", action="store", type=str,
                   help="Logfile for all incoming NMEA sentences")
    p.add_argument("-t", "--trace", action="store", type=str)
    p.add_argument('-f', '--filter', action='store', type=str)
    p.add_argument('-of', '--output_file', action='store', type=str)
    return p


def file_input(filename, pgn_active, outfd=sys.stdout):
    fd = open(filename, "r")
    print(pgn_active)
    for line in fd.readlines():
        line = line.strip('\n\r')
        # print(line)
        sep_index = line.index('|')
        timestamp = line[:sep_index]
        # print(line, sep_index, timestamp)
        fields = line[sep_index+1:].split(',')
        pgn = int(fields[1])
        if len(pgn_active) != 0:
            if pgn not in pgn_active:
                continue
        prio = int(fields[2])
        sa = int(fields[3])
        da = int(fields[4])
        payload = base64.b64decode(fields[6])
        msg = J1939_msg(pgn, prio, sa, da, payload)
        outfd.write(timestamp)
        outfd.write('|')
        outfd.write(str(msg))
        outfd.write('\n')
        res = msg.decode()
        if res is not None:
            outfd.write(str(res))
            outfd.write('\n')
            if msg.pgn == 126992:
                o = J1939Factory.build(msg, res['fields'])
        outfd.flush()


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


class N2kTracePublisher(Publisher):

    def __init__(self, opts):
        super().__init__(opts)

    def process_msg(self, msg):
        res = msg.decode()
        if res is not None:
            print(res)
        return True


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
    print("analyzing file:", opts.xml)
    defs = PGNDefinitions.build_definitions(opts.xml)
    if opts.print is not None:
        defs.print_summary()
    if opts.csv_out is not None:
        print("Generating PGN CSV file %s" % opts.csv_out)
        fp = open(opts.csv_out, 'w')
        w = csv.writer(fp, dialect='excel')
        for pgn in defs.pgns():
            w.writerow([pgn.id, pgn.name])
        fp.close()
    elif opts.input is not None:
        pgn_active = []
        if opts.filter is not None:
            print(opts.filter)
            pgn_list_s = opts.filter.split(',')
            for s in pgn_list_s:
                pgn_active.append(int(s))
        if opts.output_file is not None:
            ofd = open(opts.output_file, "w")
        else:
            ofd = sys.stdout
        file_input(opts.input, pgn_active, ofd)


if __name__ == '__main__':
    main()