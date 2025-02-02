#-------------------------------------------------------------------------------
# Name:        arguments.py
# Purpose:     runtime arguments processing
#
# Author:      Laurent Carré
#
# Created:     26/02/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import os
from argparse import ArgumentParser


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-s', '--settings', action='store', type=str, default='settings.yml')
    p.add_argument('-d', '--working_dir', action='store', type=str, default=None)
    p.add_argument("-t", "--timer", action='store', type=float, default=None)
    p.add_argument('-v', '--version', action='store_true', help='print the version and exit')

    return p


def init_options(default_base_dir: str, parser_def=_parser):
    '''
    This functions init the options versus the command line and adjust working directory
    '''
    parser = parser_def()
    opts = parser.parse_args()
    if opts.working_dir is not None:
        os.chdir(opts.working_dir)
        # new in version 2.2 keep the current dir if no working dir argument
    return opts


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
