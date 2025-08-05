#-------------------------------------------------------------------------------
# Name:        relays.py
# Purpose:     relays control classes
#
# Author:      Laurent Carré
#
# Created:     09/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time

from navigation_server.nav_gpio.nav_gpio_if import *
from navigation_server.nav_gpio.stnc_gpio_conf import STNC_Gpio_Set

_logger = logging.getLogger("ShipDataServer."+__name__)


class Relay:

    def __init__(self, name):
        self._group = STNC_Gpio_Set.get_group(name)


class LatchingRelay(Relay):

    def __init__(self, name):
        super().__init__(name)

    def reset(self):
        self._group.set_line_value('open', 0)
        self._group.set_line_value('close', 0)

    def open(self):
        self._group.pulse_line('open', 0.005)

    def close(self):
        self._group.pulse_line('close', 0.005)

    def is_open(self) -> bool:
        if self._group.get_line_value('sense') == 0:
            return True
        else:
            return False

    def position(self) -> str:
        if self._group.get_line_value('sense') == 0:
            return 'open'
        else:
            return 'close'


def main():
    _logger.setLevel(logging.DEBUG)
    relay = 'relay1'
    relay1 = LatchingRelay(relay)
    print(f"{relay} current position:", relay1.position())
    if relay1.is_open():
        print(f"{relay} open we close it")
        relay1.close()
        command = 'close'
    else:
        print(f"{relay} is closed => open")
        relay1.open()
        command = 'open'
    position = relay1.position()
    print(f'the {relay} is in position', position, 'command=', command)
    if position != command:
        print("Relay command error => reset")
        relay1.reset()

if __name__ == '__main__':
    main()
