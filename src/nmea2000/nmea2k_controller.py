#-------------------------------------------------------------------------------
# Name:        NMEA2K-controller
# Purpose:     Analyse and process NMEA2000 network control messages
#
# Author:      Laurent Carré
#
# Created:     21/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import threading
import queue
import time

from nmea_routing.server_common import NavigationServer
from nmea_routing.nmea2000_msg import NMEA2000Msg, PgnRecord
from nmea2000.nmea2k_pgndefs import N2KUnknownPGN, N2KDecodeResult

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NMEA2000Device:
    '''
    This class holds the view of the devices on the NMEA2000 Network
    '''

    def __init__(self, address):
        self._address = address
        _logger.info("NMEA Controller new device detected at address %d" % address)
        self._lastmsg_ts = 0
        self._pgn_received = {}
        self._process_vector = { 60928: self.p60928,
                                 126996: self.p126996
                                 }

    def receive_msg(self, msg: NMEA2000Msg):
        _logger.debug("New message PGN %d for device @%d" % (msg.pgn, self._address))
        self._lastmsg_ts = time.time()
        try:
            pgn_def = self.add_pgn_count(msg.pgn)
        except N2KUnknownPGN:
            return
        try:
            process_function = self._process_vector[msg.pgn]
        except KeyError:
            return
        try:
            pgn_data = pgn_def.pgn_def.decode_pgn_data(msg.payload)
        except N2KDecodeResult:
            return
        process_function(pgn_data)

    def add_pgn_count(self, pgn) -> PgnRecord:
        try:
            pgn_def = self._pgn_received[pgn]
            pgn_def.tick()
        except KeyError:
            pgn_def = PgnRecord(pgn, 0)
            self._pgn_received[pgn] = pgn_def
        return pgn_def

    def p60928(self, msg_data):
        _logger.debug("Processing ISO address claim for address %d" % self._address)
        _logger.debug("PGN data= %s" % msg_data)
        self._mfg_code = msg_data['fields']["Manufacturer Code"]

    def p126996(self, msg_data):
        _logger.debug("Processing Product information for address %d" % self._address)


class NMEA2KController(NavigationServer, threading.Thread):

    def __init__(self, opts):
        super().__init__(opts)
        threading.Thread.__init__(self, name=self._name)
        queue_size = opts.get('queue_size', int, 20)
        self._input_queue = queue.Queue(queue_size)
        self._stop_flag = False
        self._devices = {}
        _logger.info("%s debug level %d" % (__name__, _logger.getEffectiveLevel()))

    def server_type(self):
        return 'NMEA200_CONTROLLER'

    def send_message(self, msg: NMEA2000Msg):
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
            self.process_msg(msg)

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
        device = self.check_device(msg.sa)
        device.receive_msg(msg)
