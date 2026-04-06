# -------------------------------------------------------------------------------
# Name:        NMEA2K-controller
# Purpose:     Analyse and process NMEA2000 network control messages
#
# Author:      Laurent Carré
#
# Created:     21/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import threading
import queue
import time
from typing import Generator

from navigation_server.router_common import NavigationServer, NavThread, set_global_var, resolve_ref, NavigationCriticalError, N2K_MSG
from navigation_server.router_core import NMEA2000Msg
from .nmea2k_iso_messages import ISORequest
from .nmea2k_device import NMEA2000Device

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KReadTimeOut(Exception):
    pass

class N2KReadSubscriber:

    def __init__(self, client: str, select_source: list, reject_source: list, select_pgn: list, reject_pgn: list,
                 timeout=60.00):
        self._client = client
        self._queue = queue.Queue(20)
        self._select_source = None
        self._reject_source = None
        if len(select_source) > 0:
            self._select_source = {sa for sa in select_source}
        elif len(reject_source) > 0:
            self._reject_source = {sa for sa in reject_source}
        self._select_pgn = None
        self._reject_pgn = None
        if len(select_pgn) > 0:
            self._select_pgn = {pgn for pgn in select_pgn}
        elif len(reject_pgn) > 0:
            self._reject_pgn = {pgn for pgn in reject_pgn}
        self._timeout = timeout

    @property
    def client(self):
        return self._client

    def get_message(self) -> NMEA2000Msg:
        try:
            return self._queue.get(block=True, timeout=self._timeout)
        except queue.Empty:
            raise N2KReadTimeOut

    def push_message(self, msg: NMEA2000Msg):
        if self._select_source is not None:
            if msg.sa not in self._select_source:
                return
        elif self._reject_source is not None:
            if msg.sa in self._reject_source:
                return
        if self._select_pgn is not None:
            if msg.pgn not in self._select_pgn:
                return
        elif self._reject_pgn is not None:
            if msg.pgn in self._reject_pgn:
                return
        try:
            self._queue.put(msg, block=False)
        except queue.Full:
            _logger.error(f"N2KReadSubscriber queue for {self._client} full, ignoring message")
            raise



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
        set_global_var('N2KController', self)
        self._subscriber = {}
        self._max_silent = opts.get('max_silent', float, 60.0)
        self._gc_timer = threading.Timer(self._max_silent, self.device_gc)
        self._gc_lock = threading.Lock()
        self._coupler = None
        # remote access
        self._read_subscribers = {}  # 2025-06-10 changed to dictionary
        self._read_subscribers_lock = threading.Lock()
        self._interface_name = opts.get('interface', str, None)
        self._interface = None

    def server_type(self):
        return 'NMEA2000_CONTROLLER'

    def running(self) -> bool:
        return self.is_alive()

    def network_addresses(self):
        return self._devices.keys()

    def set_coupler(self, coupler):
        self._coupler = coupler

    @property
    def min_queue_size(self):
        return 20

    @property
    def input_queue(self) -> queue.Queue:
        return self._input_queue

    def start(self):
        if self._interface_name is not None:
            try:
                self._interface = resolve_ref(self._interface_name)
            except KeyError:
                _logger.critical(f"")
                raise NavigationCriticalError
            self._interface.set_controller(self)
            # self._interface.start()

        super().start()

    def delete_device(self, address):
        del self._devices[address]

    def send_message(self, msg: NMEA2000Msg):
        if not self.is_alive():
            # the thread is not running=> warning and discard
            _logger.error("NMEA Controller thread not running")
            return
        _logger.debug("NMEA2000 Controller send msg PGN%d from:%d queue size:%d" % (msg.pgn, msg.sa, self._input_queue.qsize()))
        try:
            self._input_queue.put(msg, block=False)
        except queue.Full:
            _logger.warning(f"NMEA2000 Controller input queue full message discarded: PGN{msg.pgn} SA:{msg.sa}")

    def nrun(self) -> None:
        _logger.info("%s NMEA2000 Controller starts" % self._name)
        self._gc_timer.start()
        while not self._stop_flag:
            try:
                msg = self._input_queue.get(block=True, timeout=1.0)
            except queue.Empty:
                continue
            _logger.debug("NMEA Controller input %s" % str(msg))
            if msg.type != N2K_MSG:
                _logger.info(f"NMEA2000 Controller input not NMEA2000")
                continue
            # further processing here
            try:
                self.process_msg(msg)
            except Exception as e:
                _logger.error("%s NMEA2000 Controller processing error:%s on message %s" % (self._name, e, msg.format1()))

       # end of run loop
        _logger.info("%s NMEA2000 Controller stops" % self._name)

    def stop(self):
        self._stop_flag = True
        if self._gc_timer is not None:
            self._gc_timer.cancel()

    def add_read_subscriber(self, client, select_source:list, reject_source:list, select_pgn:list, reject_pgn:list, timeout:float) -> N2KReadSubscriber:
        self._read_subscribers_lock.acquire()
        sub = N2KReadSubscriber(client, select_source, reject_source, select_pgn, reject_pgn, timeout)
        self._read_subscribers[client] = sub
        self._read_subscribers_lock.release()
        return sub

    def remove_read_subscriber(self, client):
        self._read_subscribers_lock.acquire()
        try:
            del self._read_subscribers[client]
        except KeyError:
            _logger.error(f"CAN Read subscribers removing non existing client {client} => ignored")
            pass
        self._read_subscribers_lock.release()

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

    def process_msg(self, msg: NMEA2000Msg) -> bool:
        '''
        Process incoming messages for Proxy devices or in case on indirect access to CAN
        Args:
            msg (): NMEA2000Msg

        Returns:

        '''
        if msg.sa >= 254:
            return True
        self.record_stat(msg.sa, msg.pgn)
        _logger.debug("NMEA2000 Controller process msg %s" % msg.format1())
        self._gc_lock.acquire()
        device = self.check_device(msg.sa)
        device.receive_msg(msg)
        self.call_subscribers(msg.pgn, msg)
        self._gc_lock.release()
        if msg.is_iso_protocol:
            return True
        else:
            # new in version 2.4.3 dispatch to all subscribers
            subscribers = list(self._read_subscribers.values())
            for subscriber in subscribers:
                try:
                    subscriber.push_message(msg)
                except queue.Full:
                    self.remove_read_subscriber(subscriber.client)
            return False

    def store_devices(self):

        filename = self._options.get('store', str, None)
        if filename is None:
            return

    def get_device(self) -> Generator[NMEA2000Device, None, None]:
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

    def poll_devices(self):
        '''
        This method is used to detect devices on the CAN network and get their properties
        It is used in case the CAN is connected via a coupler-adapter, not when directly connected to the CAN

        '''

        _logger.info("N2K Controller sending request for Product en Configuration information")
        # request the product information
        request = ISORequest(0, 255,126996)
        msg = request.nav_message()
        self._interface.send_n2k_msg(msg)
        # request the configuration information
        request = ISORequest(0, 255, 126998)
        msg = request.nav_message()
        self._interface.send_n2k_msg(msg)

    def record_stat(self, address: int, pgn: int):
        self._gc_lock.acquire()
        device = self.check_device(address)
        device.add_pgn_count(pgn)
        self._gc_lock.release()

    @property
    def channel(self):
        return self._interface.channel()

    def total_msg_raw(self) -> int:
        return self._interface.total_msg_raw()

    def total_msg_raw_out(self) -> int:
        return self._interface.total_msg_raw_out()

    def is_trace_active(self) -> bool:
        return self._interface.is_trace_active()

    def start_trace(self, file_root:str=None):
        self._interface.start_trace(file_root)

    def stop_trace(self):
        self._interface.stop_trace()

    def send_message(self, msg: NMEA2000Msg):
        self._interface.send_n2k_msg(msg)

    def send_message_from_application(self, application: str, msg: NMEA2000Msg) -> int:
        '''

        Args:
            application (): for the generic controller without applications, this is ignored. Kept for compatibility only
            msg (): NMEA2000Msg to be sent to the network

        Returns: None

        '''
        self._interface.send_n2k_msg(msg)
        return 0







