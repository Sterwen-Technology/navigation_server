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
import time
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
            if value == Value.ACTIVE:
                value = 1
            else:
                value = 0
            return value


    def set(self, value: int):
        with gpiod.request_lines(self._chip_path, consumer=f"{__name__}_set",
                                 config={self._offset: LineSettings(direction=Direction.OUTPUT)}) as request:
            if value > 0:
                val_set = Value.ACTIVE
            else:
                val_set = Value.INACTIVE
            request.set_value(self._offset, val_set)

    def pulse(self, width: float):
        with gpiod.request_lines(self._chip_path, consumer=f"{__name__}_set",
                                 config={self._offset: LineSettings(direction=Direction.OUTPUT)}) as request:
            request.set_value(self._offset, Value.ACTIVE)
            time.sleep(width)
            request.set_value(self._offset, Value.INACTIVE)

    def invert_pulse(self, width: float):
        with gpiod.request_lines(self._chip_path, consumer=f"{__name__}_set",
                                 config={self._offset: LineSettings(direction=Direction.OUTPUT)}) as request:
            request.set_value(self._offset, Value.INACTIVE)
            time.sleep(width)
            request.set_value(self._offset, Value.ACTIVE)


class GpioGroup:
    """
    All GPIO lines that control a device
    """
    def __init__(self, name: str, lines: dict):
        self._name = name
        self._lines = lines

    @property
    def name(self) -> str:
        return self._name

    def get_line_value(self, line_name):
        _logger.debug("GpioGroup %s line %s get" % (self._name, line_name))
        try:
            line = self._lines[line_name]
            value = line.get()
        except KeyError:
            _logger.error(f"Group {self._name}: Unknown GPIO line {line_name}")
            raise
        _logger.debug("GpioGroup %s line %s get value=%d" % (self._name, line_name, value))
        return value

    def set_line_value(self, line_name, value: int):
        _logger.debug("GpioGroup %s line %s set=%d" % (self._name, line_name, value))
        try:
            line = self._lines[line_name]
            line.set(value)
        except KeyError:
            _logger.error(f"Group {self._name}: Unknown GPIO line {line_name}")
            raise

    def pulse_line(self, line_name:str , width:float):
        _logger.debug("GpioGroup %s line %s pulse for=%f4.1 ms" % (self._name, line_name, width*1000.))
        try:
            line = self._lines[line_name]
            line.pulse(width)
        except KeyError:
            _logger.error(f"Group {self._name}: Unknown GPIO line {line_name}")
            raise

    def inverse_pulse_line(self, line_name: str, width: float):
        _logger.debug("GpioGroup %s line %s inverse pulse for=%f4.1 ms" % (self._name, line_name, width * 1000.))
        try:
            line = self._lines[line_name]
            line.inverse_pulse(width)
        except KeyError:
            _logger.error(f"Group {self._name}: Unknown GPIO line {line_name}")
            raise

class GpioSet:

    def __init__(self):
        self._groups = {}

    def add_group(self, group: GpioGroup):
        self._groups[group.name] = group

    def get_group(self, name:str) -> GpioGroup:
        return self._groups[name]

    def get_line_value(self, group_name, line_name):
        return self._groups[group_name].get_line_value(line_name)

    def set_line_value(self, group_name, line_name, value):
        self._groups[group_name].set_line_value(line_name, value)



