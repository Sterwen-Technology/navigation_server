#-------------------------------------------------------------------------------
# Name:        publisher
# Purpose:     Abstract class for all publishers
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import threading
import time
import queue
import logging

from .filters import FilterSet
from router_common import resolve_ref, set_hook

_logger = logging.getLogger("ShipDataServer."+__name__)

#######################################################################
#
#    Publisher classes => send messages to clients
#
########################################################################


class PublisherOverflow(Exception):
    pass


class Publisher(threading.Thread):
    '''
    Super class for all publishers
    '''
    def __init__(self, opts, internal=False, couplers=None, name=None, filters=None):
        if internal:
            self._opts = None
            self._couplers = {}
            for c in couplers:
                self._couplers[c.object_name()] = c
            self._queue_size = 40
            self._max_lost = 10
            self._active = True
            daemon = True
            object_name = "Internal Publisher %s" % name
        else:
            object_name = opts['name']
            self._opts = opts
            self._queue_size = opts.get('queue_size', int, 20)
            self._max_lost = opts.get('max_lost', int, 5)
            inst_list = opts.getlist('couplers', str, [])
            self._active = opts.get('active', bool, True)
            self._couplers = {}
            for inst_name in inst_list:
                set_hook(inst_name, self.add_coupler)
                self._couplers[inst_name] = resolve_ref(inst_name)
            daemon = False

        self._queue_tpass = False
        super().__init__(name=name, daemon=daemon)
        self._name = object_name
        self.name = object_name
        # moving registration to start
        self._queue = queue.Queue(self._queue_size)
        self._stopflag = False
        self._nb_msg_lost = 0
        self._filters = filters
        self._filter_select = False   # meaning that all messages passing the filter are discarded

    def start(self):
        _logger.debug("Publisher %s start flag %s" % (self._name, self._active))
        if self._active:
            for inst in self._couplers.values():
                # print("Registering %s on %s" % (self._name, inst.name()))
                inst.register(self)
            super().start()

    def publish(self, msg):
        # print("Publisher %s publish msg:%s" % (self._name, msg.decode().strip('\n\r')))
        # here we implement the filtering, no need to fill the queue with useless messages
        # that is also implying that the filtering is processed in the Coupler thread
        # print("Publisher %s publish msg:%s %s" % (self._name, msg, self._filters))
        if self._filters is not None:
            _logger.debug("Publisher %s publish with filter msg:%s" % (self._name, msg))
            if self._filters.process_filter(msg):
                # the message satisfy the filter
                if not self._filter_select:
                    # this is a reject filter
                    _logger.debug("Message discarded")
                    return
            else:
                # the message does not satisfy the filter
                if self._filter_select:
                    # that is a select filter
                    _logger.debug("Message discarded")
                    return

        try:
            self._queue.put(msg, block=False)
            self._nb_msg_lost = 0
        except queue.Full:
            # need to empty the queue
            self._nb_msg_lost += 1
            _logger.warning("Overflow on connection %s total message lost %d" % (self._name, self._nb_msg_lost))
            if self._nb_msg_lost >= self._max_lost:
                raise PublisherOverflow
        qs = self._queue.qsize()
        if qs > self._queue_size / 2:
            _logger.warning("%s Publisher Queue filling up size %d" % (self._name, qs))
            self._queue_tpass = True
            time.sleep(0.2)
        if self._queue_tpass:
            if qs < 4:
                _logger.info("%s Publisher queue back to low level" % self._name)
                self._queue_tpass = False

    def deregister(self):
        for inst in self._couplers.values():
            inst.deregister(self)

    def add_coupler(self, coupler):
        self._couplers[coupler.object_name()] = coupler
        coupler.register(self)

    def stop(self):
        _logger.info("Stop received for %s" % self._name)
        self._stopflag = True
        self.deregister()

    def run(self) -> None:
        _logger.info("Starting Publisher %s" % self._name)
        while not self._stopflag:
            count = 0
            try:
                msg = self._queue.get(timeout=1.0)
                count += 1
            except queue.Empty:
                if self._stopflag:
                    break
                else:
                    continue
            # print("message get in Publisher %s" % msg, count, self.ident)
            if not self.process_msg(msg):
                break
        self.last_action()

        _logger.info("Stopping publisher thread %s" % self._name)

    def last_action(self):
        pass

    def process_msg(self, msg):
        _logger.critical("No message processing handler in publisher")
        return False

    def object_name(self):
        return self._name

    def descr(self):
        return "Publisher %s" % self._name

    @property
    def is_active(self) -> bool:
        return self._active


class ExternalPublisher(Publisher):
    '''
    Abstract class for all Publishers that are created via the Yaml configuration file
    It add the management of filters
    '''

    def __init__(self, opts):
        super().__init__(opts)
        filter_names = opts.getlist('filters', str)
        if filter_names is not None and len(filter_names) > 0:
            _logger.info("Publisher:%s filter set:%s" % (self.object_name(), filter_names))
            self._filters = FilterSet(filter_names)
            self._filter_select = True


class Injector(ExternalPublisher):

    def __init__(self, opts):
        super().__init__(opts)
        self._target = resolve_ref(opts['target'])
        set_hook(self._target.object_name(), self.refresh_target)

    def process_msg(self, msg):
        return self._target.send_msg_gen(msg)

    def descr(self):
        return "Injector %s" % self._name

    def refresh_target(self, target):
        self._target = target


class PrintPublisher(ExternalPublisher):

    def __init__(self, opts):
        super().__init__(opts)

    def process_msg(self, msg):
        print(msg)
        return True
