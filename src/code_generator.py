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

from nmea2000.nmea2k_manufacturers import Manufacturers
from nmea2000.nmea2k_pgndefs import PGNDefinitions
from utilities.global_variables import MessageServerGlobals
from code_generation.pgn_python_gen import PythonPGNGenerator


_version = "V1.00"


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-d', '--directory', action='store', type=str, help="Output directory",
                   default="./src/generated")
    p.add_argument('-pb', '--protobuf', action="store_true")
    p.add_argument('-py', '--python', action="store_true")

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


def main():

    opts = parser.parse_args()
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(logging.INFO)

    MessageServerGlobals.manufacturers = Manufacturers('./def/Manufacturers.N2kDfn.xml')
    MessageServerGlobals.pgn_definitions = PGNDefinitions('./def/PGNDefns.N2kDfn.xml')
    output_file_base = "nmea2000_classes_gen"
    if opts.python:
        output_file = os.path.join(opts.directory, output_file_base + ".py")
        python_gen = PythonPGNGenerator(output_file)
        python_gen.gen_classes()
        python_gen.close()


if __name__ == '__main__':
    main()
