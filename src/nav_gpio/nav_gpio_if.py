#-------------------------------------------------------------------------------
# Name:        gpio
# Purpose:     interface to libgpiod
#
# Author:      Laurent Carré
#
# Created:     20/01/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import gpiod
import logging
from gpiod import LineSettings
from gpiod.line import Direction, Value

_logger = logging.getLogger("ShipDataServer."+__name__)

class GpioLine:
    """
    This class holds the data linked to a GPIO line
    and also possible actions on it
    """

    def __init__(self, chip_path:str, offset: int):

        self._chip_path = chip_path
        self._offset = offset
        if not gpiod.is_gpiochip_device(chip_path):
            _logger.error(f"GPIO interface wrong chip path:{chip_path}")
            raise ValueError

    def get(self):
        with gpiod.request_lines(self._chip_path, consumer=f"{__name__}_get",
                                  config={self._offset: LineSettings(direction=Direction.INPUT)}) as request:
            value = request.get_value(self._offset)
            _logger.info(f"GPIO chip {self._chip_path}:{self._offset}= {value}")
            return value


    def set(self, value: int):
        with gpiod.request_lines(self._chip_path, consumer=f"{__name__}_set",
                                 config={self._offset: LineSettings(direction=Direction.OUTPUT)}) as request:
            if value > 0:
                val_set = Value.ACTIVE
            else:
                val_set = Value.INACTIVE
            request.set_value(self._offset, val_set)






