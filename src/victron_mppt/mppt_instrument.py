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
from vedirect_pb2_grpc import  *

from src.instrument import *
from src.nmea0183 import XDR

_logger = logging.getLogger("ShipDataServer")


class MPPT_Instrument(Instrument):

    def __init__(self, opts):

        super().__init__(opts)
        port = opts.get('port', int, 4601)
        address = opts.get('address', str, '127.0.0.1')
        self._address = "%s:%d" % (address, port)
        self._channel = grpc.insecure_channel(self._address)
        self._stub = solar_mpptStub(self._channel)
        self._lock = threading.Semaphore()

    def get_output(self):
        req = request()
        req.id = 1
        try:
            return self._stub.GetOutput(req)
        except grpc.RpcError as err:
            _logger.error(str(err))
            raise InstrumentReadError

    def timer_lapse(self):
        self._lock.release()
        super().timer_lapse()

    def read(self):
        self._lock.acquire()
        result = self.get_output()
        sentence = XDR()
        sentence.add_transducer('A', "%f5.2" % result.current, 'A', 'MPPT Current')
        sentence.add_transducer('V', "%f5.2" % result.voltage, 'V', 'DC Circuit Voltage')
        sentence.add_transducer('W', "%f5.1" % result.panel_power, 'W', 'Solar Panel Power')
        return sentence.message()










