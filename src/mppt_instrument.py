#-------------------------------------------------------------------------------
# Name:        mppt_instrument
# Purpose:     classes to manage Victron MPPT as an instrument
#
# Author:      Laurent Carré
#
# Created:     31/03/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import grpc
import threading
from vedirect_pb2 import *
from vedirect_pb2_grpc import *

from instrument import *
from nmea0183 import XDR, NMEA0183SentenceMsg

_logger = logging.getLogger("ShipDataServer")


class MPPT_Instrument(Instrument):

    def __init__(self, opts):

        super().__init__(opts)
        port = opts.get('port', int, 4601)
        address = opts.get('address', str, '127.0.0.1')
        self._address = "%s:%d" % (address, port)
        self._channel = None
        self._stub = None
        self._lock = threading.Semaphore()

    def open(self):
        self._channel = grpc.insecure_channel(self._address)
        self._stub = solar_mpptStub(self._channel)
        self._state = self.OPEN
        return True

    def get_output(self):
        _logger.debug("MPPT GPRC request get_output")
        req = request()
        req.id = 1
        try:
            ret_val = self._stub.GetOutput(req)
            self._state = self.ACTIVE
            return ret_val
        except grpc.RpcError as err:
            _logger.error(str(err))
            self._state = self.NOT_READY
            raise InstrumentReadError

    def timer_lapse(self):
        _logger.debug("MPPT instrument timer lapse releasing lock")
        self._lock.release()
        super().timer_lapse()

    def read(self):
        _logger.debug("MPPT Instrument waiting for timer")
        self._lock.acquire()
        result = self.get_output()
        _logger.debug("MPPT output request successful")
        sentence = XDR()
        sentence.add_transducer('I', "%.2f" % result.current, 'A', 'MPPT Current')
        sentence.add_transducer('U', "%.2f" % result.voltage, 'V', 'DC Circuit Voltage')
        sentence.add_transducer('W', "%.1f" % result.panel_power, 'W', 'Solar Panel Power')
        return NMEA0183SentenceMsg(sentence)

    def stop(self):
        self._lock.release()
        super().stop()

    def close(self):
        pass





