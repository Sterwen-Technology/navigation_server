#-------------------------------------------------------------------------------
# Name:        modem_gpio.py
# Purpose:     modem control via gpio  class
#
# Author:      Laurent Carré
#
# Created:     06/06/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time

from navigation_server.nav_gpio.nav_gpio_if import *
from navigation_server.nav_gpio.stnc_gpio_conf import STNC_Gpio_Set

_logger = logging.getLogger("ShipDataServer."+__name__)




class ModemGpioControl:

    def __init__(self, name):
        self._group = STNC_Gpio_Set.get_group(name)

    def reset(self):
        self._group.inverse_pulse_line('reset', 0.01)

    def power_on(self):
        self._group.set_line_value('power', 1)

    def power_off(self):
        self._group.set_line_value('power', 0)

    def flight_mode_on(self):
        self._group.set_line_value('flight_mode', 0)

    def flight_mode_off(self):
        self._group.set_line_value('flight_mode', 1)

    def gnss_enable(self):
        self._group.set_line_value('gps_enable', 1)

    def gnss_disable(self):
        self._group.set_line_value('gps_enable', 0)

    def turn_modem_on(self):
        # make sure that the reset is high
        self._group.set_line_value('reset', 1)
        self.flight_mode_off()
        self.gnss_disable()
        self.power_on()


def main():
    _logger.setLevel(logging.DEBUG)
    modem = ModemGpioControl('MODEM_EM05')
    modem.turn_modem_on()



if __name__ == '__main__':
    main()
