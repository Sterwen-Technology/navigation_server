#-------------------------------------------------------------------------------
# Name:        nmcli_interface.py
# Purpose:     provide an interface to nmcli to manage network devices and connections
#              That shall replace the existing ad-hoc quectel_modem Python library
# Author:      Laurent Carré
#
# Created:     27/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import json
import subprocess
import sys

_logger = logging.getLogger('ShipDataServer.' + __name__)


class NetworkManagerError(Exception):
    pass


def nmcli_request(command: list):
    """
    Sends a request to nmcli and returns a generator of list of tokens
    No interpretation
    """
    args = ["nmcli", "-t"] + command
    result = subprocess.run(args, capture_output=True, encoding="utf-8")
    if result.returncode == 0:
        for line in result.stdout:
            tokens = line.split(":")
            yield tokens
    else:
        _logger.error(result.stderr)
        raise NetworkManagerError(result.returncode)
    return


class NetworkManagerControl:

    def __init__(self):
        self._devices = {}
        self._connections = {}

