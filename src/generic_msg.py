#-------------------------------------------------------------------------------
# Name:        NMEA
# Purpose:      Utilities to analyse and generate NMEA sentences
#
# Author:      Laurent Carré
#
# Created:     10/04/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

(NULL_MSG, N0183_MSG, N2K_MSG) = range(100, 103)


class NavGenericMsg:

    def __init__(self, msg_type, raw=None, msg=None):
        if msg_type not in [NULL_MSG, N0183_MSG, N2K_MSG]:
            raise ValueError
        self._type = msg_type
        self._msg = msg
        self._raw = raw

    @property
    def type(self):
        return self._type

    @property
    def msg(self):
        return self._msg
