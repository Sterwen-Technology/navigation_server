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


from navigation_server.nmea2000_datamodel import initialize_feature
from navigation_server.router_common import set_root_package, init_options, NavigationLogSystem, N2KDefinitionError
from navigation_server.code_generation import nmea2000_gen_meta, ProtobufPGNGenerator, PythonPGNGenerator

_version = "V2.2"


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-d', '--python_dir', action='store', type=str, help="Python output directory",
                   default="./navigation_server/generated")
    p.add_argument('-po', '--protobuf_dir', action='store', type=str, help="Protobuf output directory",
                   default="./navigation_server/protobuf")
    p.add_argument('-pb', '--protobuf', action="store_true", help="generate protobuf definitions")
    p.add_argument('-py', '--python', action="store_true", help="generate Python code")
    p.add_argument('-cv', '--protobuf_conv', action="store_true", help="generate Python <-> Protobuf conversion")
    p.add_argument('-ro', '--read_only', action="store_true", help="generate all classes read only")
    p.add_argument("-pgn", "--pgn", action="store", type=int, default=0, help="generate a specific PGN only")
    p.add_argument('-c', '--category', action='store', type=str, choices=['iso', 'data', 'all'],
                   default='all', help="generate a specific category (iso/data/all)")
    p.add_argument('-o', '--output', action='store', type=str, default=None, help="output file name without extension")
    p.add_argument('-wd', '--working_dir', action='store', type=str, default=None)

    return p


_logger = logging.getLogger("ShipDataServer")


def code_generator():

    opts = init_options(".", parser_def=_parser)
    set_root_package(code_generator)
    # set log for the configuration phase
    NavigationLogSystem.create_log("NMEA2000 Code generator version %s - copyright Sterwen Technology 2021-2025" % _version)
    NavigationLogSystem.log_start_string()
    try:
        _logger.setLevel(logging.ERROR)
        initialize_feature()
    except N2KDefinitionError as err:
        _logger.error(f"Error reading NMEA2000 definition: {err}")
        return

    if opts.pgn != 0:
        output_file_base = f"nmea2000_{opts.pgn}class_gen"
        _logger.setLevel(logging.DEBUG)
    else:
        if opts.output is None:
            _logger.warning("No output file name specified =use default")
            output_file_base = "nmea2000_classes_gen"
        else:
            output_file_base = opts.output
    _logger.setLevel(logging.INFO)
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
    code_generator()
