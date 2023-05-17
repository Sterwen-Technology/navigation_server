#-------------------------------------------------------------------------------
# Name:        filters
# Purpose:     classes to implement NMEA messages filtering
#
# Author:      Laurent Carré
#
# Created:     16/05/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
from nmea_routing.generic_msg import N0183_MSG, N2K_MSG, NavGenericMsg
from nmea_routing.nmea0183 import NMEA0183Msg
from nmea_routing.nmea2000_msg import NMEA2000Msg
from nmea_routing.configuration import NavigationConfiguration

_logger = logging.getLogger('ShipDataServer.' + __name__)


class NMEAFilter:

    def __init__(self, opts):
        self._name = opts['name']
        self._action = opts.get('action', str, None)
        _logger.debug("Creating filter %s" % self._name)

    @property
    def name(self):
        return self._name


class NMEA0183Filter(NMEAFilter):

    def __init__(self, opts):
        super().__init__(opts)
        self._talker = opts.get('talker', str, None)
        if self._talker is not None:
            self._talker = self._talker.encode()
        self._formatter = opts.get('formatter', str, None)
        if self._formatter is not None:
            self._formatter = self._formatter.encode()

    def valid(self) -> bool:
        if self._talker is not None or self._formatter is not None:
            return True
        else:
            return False

    def process_nmea0183(self, msg: NMEA0183Msg) -> bool:

        if self._talker is None or self._talker == msg.talker():
            talker = True
        else:
            talker = False
        # _logger.debug("Filter formatter %s with %s" % (self._formatter, msg.formatter()))
        if self._formatter is None or self._formatter == msg.formatter():
            formatter = True
        else:
            formatter = False
        result = talker and formatter
        if result:
            _logger.debug("Processing NMEA0183 filter %s with message %s ==>> discard" % (self._name, msg))
        return result


class NMEA2000Filter(NMEAFilter):

    def __init__(self, opts):
        super().__init__(opts)
        self._pgns = opts.getlist('pgn', int, None)
        self._sa = opts.get('source', int, None)

    def valid(self) -> bool:
        if self._pgns is not None or self._sa is not None:
            return True
        else:
            return False

    def process_n2k(self, msg: NMEA2000Msg) -> bool:
        # _logger.debug("Processing filter %s with message %s" % (self._name, msg.format2()))
        if self._sa is None or self._sa == msg.sa:
            sa = True
        else:
            sa = False
        if self._pgns is None or msg.pgn in self._pgns:
            pgn = True
        else:
            pgn = False
        result = sa and pgn
        if result:
            _logger.debug("Processing N2K filter %s with message %s ==>> discard" % (self._name, msg.format2()))
        return result


class FilterSet:

    def __init__(self, filter_ref_list=None):
        self._nmea0183_filters = []
        self._n2k_filters = []
        if filter_ref_list is not None:
            for fn in filter_ref_list:
                try:
                    f = NavigationConfiguration.get_conf().get_object(fn)
                except KeyError:
                    _logger.error("Filter reference %s non existent" % fn)
                    continue
                self.add_filter(f)

    def add_filter(self, f):
        _logger.debug("Adding filter in set name:%s valid: %s" % (f.name, f.valid()))
        if f.valid():
            if isinstance(f, NMEA0183Filter):
                _logger.debug("Adding NMEA0183 Filter %s" % f.name)
                self._nmea0183_filters.append(f)
            elif isinstance(f, NMEA2000Filter):
                _logger.debug("Adding NMEA2000 Filter %s" % f.name)
                self._n2k_filters.append(f)

    def process_filter(self, msg) -> bool:
        _logger.debug("Filtering %s" % msg.printable())
        try:
            if msg.type == N0183_MSG:
                for f in self._nmea0183_filters:
                    if f.process_nmea0183(msg.msg):
                        return True
            elif msg.type == N2K_MSG:
                for f in self._n2k_filters:
                    if f.process_n2k(msg.msg):
                        return True
        except Exception as e_all:
            _logger.error("Filtering error: %s" % e_all)
        return False

