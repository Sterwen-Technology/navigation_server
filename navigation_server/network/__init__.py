#-------------------------------------------------------------------------------
# Name:        __init__.py
# Purpose:     network package
#              Add USB modem management in the navigation_server environment to simplify deployment
# Author:      Laurent Carré
#
# Created:     30/01/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
from .usb_modem_at_lib import UsbATModem, VisibleOperator, ModemException
from .quectel_modem import QuectelModem
