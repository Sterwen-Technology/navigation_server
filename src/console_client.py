#-------------------------------------------------------------------------------
# Name:        Console Client
# Purpose:     Console client interface via GPRC for navigation server
#
# Author:      Laurent Carré
#
# Created:     04/05/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import grpc

from console_pb2 import *
from console_pb2_grpc import *

_logger = logging.getLogger("ShipDataClient")


class InstrumentProxy:

    def __init__(self, msg: InstrumentMsg):
        self._msg = msg

    @property
    def name(self):
        return self._msg.name

    @property
    def state(self):
        return self._msg.DESCRIPTOR.fields_by_name['state'].enum_type.values_by_number[self._msg.state].name

    @property
    def dev_state(self):
        return self._msg.DESCRIPTOR.fields_by_name['dev_state'].enum_type.values_by_number[self._msg.dev_state].name

    @property
    def protocol(self):
        return self._msg.protocol

    @property
    def msg_in(self):
        return self._msg.msg_in

    @property
    def msg_out(self):
        return self._msg.msg_out


class ConsoleClient:

    def __init__(self, address):
        self._channel = grpc.insecure_channel(address)
        self._stub = NavigationConsoleStub(self._channel)
        self._req_id = 0
        _logger.info("Console on navigation server %s" % address)

    def get_instruments(self):
        instruments = []
        req = Request(id=self._req_id)
        try:
            for inst in self._stub.GetInstruments(req):
                instruments.append(InstrumentProxy(inst))
            return instruments
        except Exception as err:
            _logger.error("Error accessing server:%s" % err)
            return None

