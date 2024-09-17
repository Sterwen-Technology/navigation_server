#-------------------------------------------------------------------------------
# Name:        code generator
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     23/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import os
import logging
from argparse import ArgumentParser

from nmea2000_datamodel import Manufacturers
from nmea2000_datamodel import PGNDefinitions
from router_common.global_variables import MessageServerGlobals
from code_generation import nmea2000_gen_meta, ProtobufPGNGenerator, PythonPGNGenerator

_version = "V1.01"


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-d', '--python_dir', action='store', type=str, help="Python output directory",
                   default="./src/generated")
    p.add_argument('-po', '--protobuf_dir', action='store', type=str, help="Protobuf output directory",
                   default="./src/protobuf")
    p.add_argument('-pb', '--protobuf', action="store_true", help="generate protobuf definitions")
    p.add_argument('-py', '--python', action="store_true", help="generate Python code")
    p.add_argument('-cv', '--protobuf_conv', action="store_true", help="generate Python <-> Protobuf conversion")
    p.add_argument('-ro', '--read_only', action="store_true", help="generate all classes read only")
    p.add_argument("-pgn", "--pgn", action="store", type=int, default=0, help="generate a specific PGN only")
    p.add_argument('-c', '--category', action='store', type=str, choices=['iso', 'data', 'all'],
                   default='all', help="generate a specific category (iso/data/all)")
    p.add_argument('-o', '--output', action='store', type=str, default=None, help="output file name without extension")

    return p


parser = _parser()
_logger = logging.getLogger("ShipDataServer")


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

    opts = parser.parse_args()
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(logging.INFO)

    MessageServerGlobals.manufacturers = Manufacturers('./def/Manufacturers.N2kDfn.xml')
    MessageServerGlobals.pgn_definitions = PGNDefinitions('./def/PGNDefns.N2kDfn.xml')
    if opts.pgn != 0:
        output_file_base = f"nmea2000_{opts.pgn}class_gen"
        _logger.setLevel(logging.DEBUG)
    else:
        if opts.output is None:
            _logger.warning("No output file name specified =use default")
            output_file_base = "nmea2000_classes_gen"
        else:
            output_file_base = opts.output

    _logger.info("Generating NMEA2000 meta model")
    class_list = nmea2000_gen_meta(opts.category, pgn=opts.pgn)
    _logger.info(f"Generated meta model for {len(class_list)} PGN")
    if opts.python:
        output_file = os.path.join(opts.python_dir, output_file_base + ".py")
        python_gen = PythonPGNGenerator(output_file, opts.read_only)
        python_gen.gen_classes(class_list, opts.protobuf_conv, output_file_base)
        python_gen.close()
    if opts.protobuf:
        output_file = os.path.join(opts.protobuf_dir, output_file_base + ".proto")
        protobuf_gen = ProtobufPGNGenerator(output_file)
        protobuf_gen.gen_messages(class_list)
        protobuf_gen.close()


if __name__ == '__main__':
    main()
