import sys
import logging

from navigation_server.nav_gpio import *

_logger = logging.getLogger("ShipDataServer")

def main():
    _logger.setLevel(logging.DEBUG)
    value = STNC_Gpio_Set.set_line_value(sys.argv[1], sys.argv[2], int(sys.argv[3]))
    print(f"{sys.argv[1]}-{sys.argv[2]} = {value}")


if __name__ == '__main__':
     main()