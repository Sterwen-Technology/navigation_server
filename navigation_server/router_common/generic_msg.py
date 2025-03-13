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


import logging

_logger = logging.getLogger("ShipDataServer."+__name__)

(NULL_MSG, TRANSPARENT_MSG, N0183_MSG, N2K_MSG, N0183D_MSG) = range(100, 105)


class NavGenericMsg:

    __slots__ = ('_type', '_msg', '_raw', '_datalen')

    def __init__(self, msg_type, raw=None, msg=None):
        if msg_type not in (NULL_MSG, TRANSPARENT_MSG, N0183_MSG, N2K_MSG, N0183D_MSG):
            raise ValueError
        self._type = msg_type
        # self._raw = raw
        if self._type == N0183_MSG:
            if msg is None:
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
            else:
                _logger.error("Cannot create a NMEA0183 message from another one")
                raise ValueError
            self._msg = self

        elif self._type == N2K_MSG:
            self._raw = raw  # keep raw message for transparency
            self._msg = msg
            if msg is None:
                self._type = NULL_MSG
        elif self.type == TRANSPARENT_MSG:
            self._raw = raw
            self._msg = msg

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
            if type(self._raw) is str:
                return self._raw
            else:
                return self._raw.decode().strip('\r\n')
        else:
            return "NULL"

    def dump(self) -> str :
        if self._raw is not None:
            raw_str = self._raw.hex().decode()
        else:
            raw_str = "None"
        return "%s raw:%s" % (self.printable(), raw_str)

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

    def is_iso_protocol(self) -> bool:
        if self._type == N2K_MSG:
            if self._msg.is_iso_protocol:
                return True
        return False

    def __str__(self):
        return self.printable()
