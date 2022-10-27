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

(NULL_MSG, TRANSPARENT_MSG, N0183_MSG, N2K_MSG) = range(100, 104)


class NavGenericMsg:

    def __init__(self, msg_type, raw=None, msg=None):
        if msg_type not in [NULL_MSG, TRANSPARENT_MSG, N0183_MSG, N2K_MSG]:
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
                lt = len(raw)
                i1 = lt - 2
                if raw[i1:lt] == b'\r\n':
                    self._datalen = i1
                else:
                    self._raw.extend(b'\r\n')
                    self._datalen = lt

        elif self._type == N2K_MSG:
            self._raw = None
            if msg is None:
                self._type = NULL_MSG
        elif self.type == TRANSPARENT_MSG:
            self._raw = raw

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
        elif self._type == TRANSPARENT_MSG:
            return self._raw.decode().strip('\r\n')
        else:
            return "NULL"

    def as_protobuf(self, msg):
        '''
        For NMEA0183 messages the method is called directly (subclass)
        So this is only for NMEA2000
        Other cases are illegal
        :return:
        '''
        if self._type == N2K_MSG:
            return self._msg.as_protobuf(msg)
        else:
            raise ValueError
