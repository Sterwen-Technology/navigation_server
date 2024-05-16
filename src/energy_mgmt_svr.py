#-------------------------------------------------------------------------------
# Name:        energy_mgmt_svr
# Purpose:     server for all energy related functions
#
# Author:      Laurent Carré
#
# Created:     16/05/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import logging
import sys
import os
from argparse import ArgumentParser
from concurrent import futures
# sys.path.insert(0, "/data/solidsense/navigation/src")

from victron_mppt.mppt_reader import VEdirect_simulator, Vedirect, GrpcServer, VEDirectException
from utilities.arguments import init_options

_version = "V1.01"


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-i', '--interface', action='store', type=str, default='/dev/ttyUSB4')
    p.add_argument('-p', '--port', action="store", type=int, default=4505)
    p.add_argument('-d', '--working_dir', action='store', type=str)
    # p.add_argument('-s', '--serial_port', action="store", default=4507)
    p.add_argument('-sim', '--simulator', action="store")

    return p


_logger = logging.getLogger("Energy_Server")
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"

def main():
    opts = init_options(default_base_dir, _parser)
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(logging.INFO)

    _logger.info("Victron MPPT VEdirect reader version %s" % _version)
    ser_emu = None
    if opts.simulator is not None:
        reader = VEdirect_simulator(opts.simulator, ser_emu)
    else:
        try:
            reader = Vedirect(opts.interface, 10.0, ser_emu)
        except (VEDirectException, IOError, BrokenPipeError):
            _logger.critical("Unrecoverable error => stopping the service")
            os._exit(0)

    server = GrpcServer(opts, reader)
    if ser_emu is not None:
        ser_emu.start()
    reader.start()
    server.start()

    if opts.simulator is not None:
        server.wait()
    else:
        reader.join()


if __name__ == '__main__':
    main()
