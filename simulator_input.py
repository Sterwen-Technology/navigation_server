#-------------------------------------------------------------------------------
# Name:        simulator_input
# Purpose:
#
# Author:      Laurent
#
# Created:     17/12/2021
# Copyright:   (c) Laurent 2019
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import socket
import logging
from IPInstrument import *

_logger = logging.getLogger("ShipDataServer")


class SimulatorInput(IPInstrument):

    def __init__(self, opts):
        super().__init__(opts)
