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
        # self._raw = raw
        if self._type == N0183_MSG:
            if raw is None:
                self._type = NULL_MSG
            elif len(raw) == 0:
                self._type = NULL_MSG
            else:
                self._raw = bytearray(raw)
                self._raw.extend(b'\r\n')
                self._datalen = len(raw)
        elif self._type == N2K_MSG:
            if msg is None:
                self._type = NULL_MSG

    @property
    def type(self):
        return self._type

    @property
    def msg(self):
        return self._msg

    @property
    def raw(self):
        return self._raw

    def printable(self) -> str:
        if self._type == N0183_MSG:
            return self._raw[:self._datalen].decode()
        elif self._type == N2K_MSG:
            return str(self._msg)
        else:
            return "NULL"
