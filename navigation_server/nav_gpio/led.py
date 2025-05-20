#-------------------------------------------------------------------------------
# Name:        led
# Purpose:     led control for STNC800
#
# Author:      Laurent Carré
#
# Created:     20/5/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import os.path
import sys


class TricolorLed:

    def __init__(self):
        root = "/sys/class/leds"
        brightness = 'brightness'
        self._red_file = os.path.join(root,'R', brightness)
        self._blue_file = os.path.join(root,'B',brightness)
        self._green_file = os.path.join(root, 'G', brightness)

    @staticmethod
    def set_brightness(file, brightness:(int, float)):
        if type(brightness) is int:
            if 0 <= brightness <= 255:
                val = brightness
            else:
                raise ValueError
        elif type(brightness) is float:
            if 0.0 <= brightness <= 1.0:
                val = int(255 * brightness)
            else:
                raise ValueError
        else:
            raise TypeError
        with open(file, 'w') as fd:
            fd.write(str(val))

    def red_brightness(self, brightness:(int, float)):
        self.set_brightness(self._red_file, brightness)

    def blue_brightness(self, brightness:(int, float)):
        self.set_brightness(self._blue_file, brightness)

    def green_brightness(self, brightness:(int, float)):
        self.set_brightness(self._green_file, brightness)

STNC_D7_Led = TricolorLed()

if __name__ == '__main__':
    jump = {'red': STNC_D7_Led.red_brightness, 'green': STNC_D7_Led.green_brightness, 'blue': STNC_D7_Led.blue_brightness}
    color = sys.argv[1]
    brightness = int(sys.argv[2])
    jump[color](brightness)

