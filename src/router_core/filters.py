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
import time
from router_common import N0183_MSG, N2K_MSG
from router_common import resolve_ref

_logger = logging.getLogger('ShipDataServer.' + __name__)


class TimeFilter:

    def __init__(self, period):
        self._period = period
        self._tick_time = time.monotonic()

    def check_period(self) -> bool:
        # _logger.debug("Time filter", self._name,t, self._tick_time, self._period, t-self._tick_time)
        t = time.monotonic()
        if t - self._tick_time > self._period:
            self._tick_time += self._period

            return False
        else:
            return True


class NMEAFilter:

    def __init__(self, opts):
        self._name = opts['name']
        self._type = opts.get_choice('type', ('discard', 'select'), 'discard')
        # self._action = opts.get_choice('action', ('time_filter', 'other'), 'default')

        _logger.debug("Creating filter %s with type:%s" % (self._name, self._type))

    @property
    def name(self):
        return self._name

    def action(self, msg) -> bool:
        '''
        process the possible action if the message pass the filter
        return True if the message is selected
        '''

        if self._type == 'select':
            return False
        else:
            return True # all records are selected
        # more processing options to come

    def valid(self):
        return True

    def message_type(self):
        raise NotImplementedError



class FilterSet:

    def __init__(self, filter_ref_list=None):
        self._nmea0183_filters = []
        self._n2k_filters = []
        if filter_ref_list is not None:
            for fn in filter_ref_list:
                try:
                    f = resolve_ref(fn)
                except KeyError:
                    _logger.error("Filter reference %s non existent" % fn)
                    continue
                self.add_filter(f)
        if len(self._n2k_filters) + len(self._nmea0183_filters) <= 0:
            _logger.error("FilterSet has no filters")
            raise ValueError

    def add_filter(self, f):
        _logger.debug("Adding filter in set name:%s valid: %s" % (f.name, f.valid()))
        if f.valid():
            if f.message_type() == N0183_MSG:
                _logger.info("Adding NMEA0183 Filter %s" % f.name)
                self._nmea0183_filters.append(f)
            elif f.message_type() == N2K_MSG:
                _logger.info("Adding NMEA2000 Filter %s" % f.name)
                self._n2k_filters.append(f)
            else:
                raise TypeError

    def process_filter(self, msg, execute_action=True) -> bool:
        _logger.debug("Filtering %s" % msg)
        result = False
        try:
            if msg.type == N0183_MSG:
                for f in self._nmea0183_filters:
                    if f.process_nmea0183(msg.msg):
                        result = True
                        break
            elif msg.type == N2K_MSG:
                for f in self._n2k_filters:
                    if f.process_n2k(msg.msg):
                        result = True
                        break
        except Exception as e_all:
            _logger.error("Filtering error: %s" % e_all)
            return False
        if result:
            # the msg is in the filter, now decide what to do
            if execute_action:
                result = f.action(msg.msg)
                #if not result:
                    #print("Filter", f.name, "Validated by action")
            if result:
                _logger.debug("Filter %s => True" % f.name)
        '''
        Result is False if the message is not selected by the filter
        
        '''
        return result

