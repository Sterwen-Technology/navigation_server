#-------------------------------------------------------------------------------
# Name:        gpio configuration for STNC
# Purpose:     interface to libgpiod
#
# Author:      Laurent Carré
#
# Created:     19/02/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

from navigation_server.nav_gpio import GpioLine, GpioGroup, GpioSet

STNC_Gpio_Set = GpioSet()

STNC_Gpio_Set.add_group(GpioGroup("relay1", {"close": GpioLine("/dev/gpiochip0", 13),
                                                        "open": GpioLine("/dev/gpiochip0", 5),
                                                        "sense": GpioLine("/dev/gpiochip4", 0)}))

STNC_Gpio_Set.add_group(GpioGroup("relay2", {"close": GpioLine("/dev/gpiochip0", 12),
                                                        "open": GpioLine("/dev/gpiochip3", 22),
                                                        "sense": GpioLine("/dev/gpiochip4", 1)}))

STNC_Gpio_Set.add_group(GpioGroup("CAN1", {"standby": GpioLine("/dev/gpiochip2", 28),
                                                       "silent": GpioLine("/dev/gpiochip2", 26),
                                                       "bus_detect": GpioLine("/dev/gpiochip0", 1)}))

STNC_Gpio_Set.add_group(GpioGroup("CAN2", {"standby": GpioLine("/dev/gpiochip2", 27),
                                                       "silent": GpioLine("/dev/gpiochip2", 29),
                                                       "bus_detect": GpioLine("/dev/gpiochip0", 10)}))

