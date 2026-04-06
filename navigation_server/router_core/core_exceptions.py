#-------------------------------------------------------------------------------
# Name:        core_exceptions
# Purpose:     Regroup all exceptions from the router_core package
#
# Author:      Laurent Carré
#
# Created:     24/03/206
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

class CouplerReadError(Exception):
    pass


class CouplerWriteError(Exception):
    pass


class CouplerTimeOut(CouplerReadError):
    pass


class CouplerNotPresent(Exception):
    pass


class CouplerOpenRefused(Exception):
    pass


class PublisherOverflow(Exception):
    pass