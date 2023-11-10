#-------------------------------------------------------------------------------
# Name:        network utilities
# Purpose:     several functions to access network - Linux only
#
# Author:      Laurent Carré
#
# Created:     23/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import logging

_logger = logging.getLogger("ShipDataServer." + __name__)


def get_mac(interface: str) -> str:
    try:
        addr_file = "/sys/class/net/%s/address" % interface
        fd = open(addr_file)
    except IOError as e:
        _logger.error(str(e))
        raise
    line = fd.readline()
    fd.close()
    return line[:17]


def get_id_from_mac(source: str) -> int:
    mac = get_mac(source)
    mac_bytes = mac.split(':')
    return (int(mac_bytes[5], 16) + (int(mac_bytes[4], 16) << 8) + (int(mac_bytes[3], 16) << 16) +
               (int(mac_bytes[2], 16) << 24))
