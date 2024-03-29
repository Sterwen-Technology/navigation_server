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

from .nmea2k_device import NMEA2000Device
from router_common import NavigationServer
from router_core import NMEA2000Msg
from router_common import NavigationConfiguration

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2KController(NavigationServer, threading.Thread):

    def __init__(self, opts):
        NavigationServer.__init__(self, opts)
        threading.Thread.__init__(self, name=self._name)
        self._devices = {}
        queue_size = opts.get('queue_size', int, 20)
        self._save_file = opts.get('save_file', str, None)
        if self._save_file is not None:
            self.init_save()
        self._input_queue = queue.Queue(queue_size)
        self._stop_flag = False
        NavigationConfiguration.get_conf().set_global('N2KController', self)
        self._subscriber = {}

    def server_type(self):
        return 'NMEA2000_CONTROLLER'

    def running(self) -> bool:
        return self.is_alive()

    def network_addresses(self):
        return self._devices.keys()

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

    def run(self) -> None:
        _logger.info("%s NMEA2000 Controller starts" % self._name)
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

    def check_device(self, address: int) -> NMEA2000Device:
        try:
            return self._devices[address]
        except KeyError:
            dev = NMEA2000Device(address)
            self._devices[address] = dev
            return dev

    def process_msg(self, msg: NMEA2000Msg):
        if msg.sa >= 254:
            return
        device = self.check_device(msg.sa)
        device.receive_msg(msg)
        self.call_subscribers(msg.pgn, msg)

    def store_devices(self):
        filename = self._options.get('store', str, None)
        if filename is None:
            return

    def get_device(self) -> NMEA2000Device:
        sorted_dict = sorted(self._devices.items())
        for addr, device in sorted_dict:
            yield device

    def sort_devices(self):
        return sorted(self._devices.items())

    def get_device_by_address(self, address: int):
        try:
            return self._devices[address]
        except KeyError:
            _logger.warning('N2K No device with address:%d' % address)
        raise

    def get_device_with_property_value(self, d_property, value):
        # we use brute search
        for dev in self._devices:
            try:
                if dev.property[d_property] == value:
                    return dev
            except KeyError:
                continue
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





