# -------------------------------------------------------------------------------
# Name:        NMEA2K-controller
# Purpose:     Analyse and process NMEA2000 network control messages
#
# Author:      Laurent Carré
#
# Created:     21/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import threading
import queue
import time

from .nmea2k_device import NMEA2000Device
from router_common import NavigationServer, NavThread
from router_core import NMEA2000Msg
from router_common import NavigationConfiguration

_logger = logging.getLogger("ShipDataServer." + __name__)

class NMEA2KController(NavigationServer, NavThread):

    def __init__(self, opts):
        NavigationServer.__init__(self, opts)
        NavThread.__init__(self, name=self._name)
        self._devices = {}
        queue_size = opts.get('queue_size', int, 20)
        if queue_size < self.min_queue_size:
            queue_size = self.min_queue_size
        self._save_file = opts.get('save_file', str, None)
        if self._save_file is not None:
            self.init_save()
        self._input_queue = queue.Queue(queue_size)
        self._stop_flag = False
        NavigationConfiguration.get_conf().set_global('N2KController', self)
        self._subscriber = {}
        self._max_silent = opts.get('max_silent', float, 60.0)
        self._gc_timer = threading.Timer(self._max_silent, self.device_gc)
        self._gc_lock = threading.Lock()

    def server_type(self):
        return 'NMEA2000_CONTROLLER'

    def running(self) -> bool:
        return self.is_alive()

    def network_addresses(self):
        return self._devices.keys()

    @property
    def min_queue_size(self):
        return 20

    def delete_device(self, address):
        del self._devices[address]

    def send_message(self, msg: NMEA2000Msg):
        if not self.is_alive():
            # the thread is not running=> warning and discard
            _logger.error("NMEA Controller thread not running")
            return
        try:
            self._input_queue.put(msg, block=False)
        except queue.Full:
            _logger.warning("NMEA2000 Controller input queue full")

    def nrun(self) -> None:
        _logger.info("%s NMEA2000 Controller starts" % self._name)
        self._gc_timer.start()
        while not self._stop_flag:
            try:
                msg = self._input_queue.get(block=True, timeout=1.0)
            except queue.Empty:
                continue
            _logger.debug("NMEA Controller input %s" % msg.format1())
            # further processing here
            try:
                self.process_msg(msg)
            except Exception as e:
                _logger.error("%s NMEA2000 Controller processing error:%s on message %s" % (self._name, e, msg.format1()))

        _logger.info("%s NMEA2000 Controller stops" % self._name)

    def stop(self):
        self._stop_flag = True
        if self._gc_timer is not None:
            self._gc_timer.cancel()

    def check_device(self, address: int) -> NMEA2000Device:
        """
        Check if the device at address is already known
        If not create the internal table entry for that address.
        address: CAN address (0-253) of the device
        returns: proxy object for the device or local device
        """
        try:
            return self._devices[address]
        except KeyError:
            dev = NMEA2000Device(address)
            self._devices[address] = dev
            return dev

    def process_msg(self, msg: NMEA2000Msg):
        if msg.sa >= 254:
            return
        self._gc_lock.acquire()
        device = self.check_device(msg.sa)
        device.receive_msg(msg)
        self.call_subscribers(msg.pgn, msg)
        self._gc_lock.release()

    def store_devices(self):

        filename = self._options.get('store', str, None)
        if filename is None:
            return

    def get_device(self) -> NMEA2000Device:
        """
        generator for the list of devices known sorted by address
        list is locked to prevent any modification during the generator execution
        """
        self._gc_lock.acquire()
        sorted_dict = sorted(self._devices.items())
        for addr, device in sorted_dict:
            yield device
        self._gc_lock.release()

    def sort_devices(self):
        return sorted(self._devices.items())

    def get_device_by_address(self, address: int):
        self._gc_lock.acquire()
        try:
            dev = self._devices[address]
            self._gc_lock.release()
            return dev
        except KeyError:
            _logger.warning('N2K No device with address:%d' % address)
            self._gc_lock.release()
        raise

    def get_device_with_property_value(self, d_property, value):
        # we use brute search
        self._gc_lock.acquire()
        for dev in self._devices:
            try:
                if dev.property[d_property] == value:
                    self._gc_lock.release()
                    return dev
            except KeyError:
                continue
        self._gc_lock.release()
        raise KeyError

    def init_save(self):
        pass

    def add_subscriber(self, pgn, function):
        self._subscriber[pgn] = function

    def call_subscribers(self, pgn, msg):
        try:
            function = self._subscriber[pgn]
        except KeyError:
            return
        function(msg)

    def device_gc(self):
        '''
        Garbage collect devices that are not sending messages
        '''
        if self._stop_flag:
            return
        self._gc_lock.acquire()
        check_time = time.time()
        to_be_deleted = []
        for key, dev in self._devices.items():
            if dev.is_proxy():
                # only proxies can disappear
                if check_time - dev.last_time_seen > self._max_silent:
                    # the device has not been seen, so it shall be removed
                    _logger.info(f"NMEA2000 device at @{key} non longer active")
                    to_be_deleted.append(key)
        for key in to_be_deleted:
            del self._devices[key]
        self._gc_lock.release()
        self._gc_timer = threading.Timer(self._max_silent, self.device_gc)
        self._gc_timer.start()





