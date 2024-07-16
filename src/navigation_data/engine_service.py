#-------------------------------------------------------------------------------
# Name:        configuration
# Purpose:     Decode Yaml configuration file and manage the related objects
#
# Author:      Laurent Carré
#
# Created:     08/01/2022 - new version with features 20/03/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
from collections import namedtuple
import datetime
import time

from generated.navigation_data_pb2 import engine_data, engine_request, engine_response
from generated.navigation_data_pb2_grpc import EngineDataServicer, add_EngineDataServicer_to_server

from router_common import GrpcSecondaryService

_logger = logging.getLogger("ShipDataServer."+__name__)


class EngineDataServicerImpl(EngineDataServicer):

    def __init__(self, engine_service):

        self._engine_service = engine_service

    def GetEngineData(self, request, context):

        engine_id = request.engine_id
        response = engine_response()
        response.data.engine_id = engine_id
        try:
            self._engine_service.get_engine_data(response.data)
            response.error_message = "NO_ERROR"
        except KeyError:
            response.error_message = "NO_ENGINE"
        return response


class EngineDataService(GrpcSecondaryService):

    def __init__(self, opts):
        super().__init__(opts)
        self._servicer = None
        self._engines = {}

    def finalize(self):
        super().finalize()
        self._servicer = EngineDataServicerImpl(self)
        # now setup the subscriptions
        self._primary_service.subscribe(self, 127488, self.p127488)
        self._primary_service.subscribe(self, 127489, self.p127489)
        add_EngineDataServicer_to_server(self._servicer, self.grpc_server)

    def get_engine(self, engine_id):
        try:
            return self._engines[engine_id]
        except KeyError:
            engine = EngineData(engine_id)
            self._engines[engine_id] = engine
            return engine

    def p127488(self, msg):  # PGN127488 Engine parameters Rapid Update
        _logger.debug("EngineData processing PGN127488 on instance %d speed=%f" % (msg.engine_instance, msg.engine_speed))
        engine_id = msg.engine_instance
        engine = self.get_engine(engine_id)
        engine.new_message()
        engine.update_speed(msg.engine_speed)

    def p127489(self, msg):
        _logger.debug("EngineData processing PGN127489 on instance %d" % msg.engine_instance)
        engine_id = msg.engine_instance
        engine = self.get_engine(engine_id)
        engine.new_message()
        engine.update_data(msg)

    def get_engine_data(self, response):
        try:
            engine = self._engines[response.engine_id]
        except KeyError:
            _logger.error(f"Engine {response.engine_id} non existent")
            raise
        engine.get_data(response)


class EngineData:

    (OFF, ON, RUNNING) = range(0, 3)

    def __init__(self, engine_id:int):
        self._id = engine_id
        self._state = self.ON
        self._speed = 0.0
        self._first_on = datetime.datetime.now()
        self._last_message = time.time()
        self._temperature = 0.
        self._total_hours = 0.
        self._alternator_voltage = 0.
        self._start_time = None
        self._stop_time = None

    def update_speed(self, speed):
        if self._speed == 0.0 and speed > 0.0:
            self._state = self.RUNNING
            self._start_time = datetime.datetime.now()
        elif self._speed > 0.0 and speed == 0.0:
            self._state = self.ON
            self._stop_time = datetime.datetime.now()
        self._speed = speed

    def new_message(self):
        self._last_message = time.time()

    def update_data(self, msg):
        if self._state == self.OFF:
            self._state = self.ON
        self._temperature = msg.temperature
        self._alternator_voltage = msg.alternator_voltage
        self._total_hours = msg.total_engine_hours

    def get_data(self, response: engine_data):
        response.engine_id = self._id
        response.state = self._state
        response.total_hours = self._total_hours
        response.speed = self._speed
        response.temperature = self._temperature
        if self._start_time is not None:
            response.last_start_time = self._start_time.isoformat()
        if self._stop_time is not None:
            response.last_stop_time = self._stop_time.isoformat()

    def check_off(self):
        if self._speed == 0.0 and time.time() - self._last_message > 30.0:
            self._state = self.OFF





