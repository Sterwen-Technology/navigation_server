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
import threading
from collections import namedtuple
import datetime
import time

from generated.navigation_data_pb2 import engine_data, engine_request, engine_response, engine_event
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

    def GetEngineEvents(self, request, context):
        engine_id = request.engine_id
        response = engine_response()
        # response.data.engine_id = engine_id
        try:
            self._engine_service.get_engine_events(engine_id, response.events)
            response.error_message = "NO_ERROR"
        except KeyError:
            response.error_message = "NO_ENGINE"

        return response


class EngineDataService(GrpcSecondaryService):

    def __init__(self, opts):
        super().__init__(opts)
        self._servicer = None
        self._engines = {}
        self._timer = threading.Timer(30.0, self.check_off_engines)

    def finalize(self):
        super().finalize()
        self._servicer = EngineDataServicerImpl(self)
        # now setup the subscriptions
        self._primary_service.subscribe(self, 127488, self.p127488)
        self._primary_service.subscribe(self, 127489, self.p127489)
        add_EngineDataServicer_to_server(self._servicer, self.grpc_server)
        self._timer.start()

    def get_engine(self, engine_id):
        try:
            return self._engines[engine_id]
        except KeyError:
            engine = EngineData(engine_id)
            self._engines[engine_id] = engine
            return engine

    def check_off_engines(self):
        nb_engines = len(self._engines)
        for e in self._engines.values():
            if e.check_off():
                nb_engines -= 1
        # restart the timer in any case - let's see what we do when no engine is active
        self._timer = threading.Timer(30.0, self.check_off_engines)
        self._timer.start()

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

    def get_engine_events(self, engine_id, response):
        try:
            engine = self._engines[engine_id]
        except KeyError:
            _logger.error(f"Engine {engine_id} non existent")
            raise
        for event in engine.get_events_pb():
            response.append(event)


class EngineEvent:

    def __init__(self, total_hours, previous_state, current_state):
        self._ts = datetime.datetime.now()
        self._total_hours = total_hours
        self._previous_state = previous_state
        self._current_state = current_state

    def as_protobuf(self, engine_id):
        e_pb = engine_event()
        e_pb.engine_id = engine_id
        e_pb.timestamp = self._ts.isoformat()
        e_pb.total_hours = self._total_hours
        e_pb.current_state = self._current_state
        e_pb.previous_state = self._previous_state
        return e_pb


class EngineData:

    (OFF, ON, RUNNING) = range(0, 3)

    def __init__(self, engine_id:int):
        self._id = engine_id
        self._state = self.OFF
        self._speed = 0.0
        self._first_on = datetime.datetime.now()
        self._last_message = time.time()
        self._temperature = 0.
        self._total_hours = 0.
        self._alternator_voltage = 0.
        self._start_time = None
        self._stop_time = None
        self._day_events = []

    def update_speed(self, speed):
        if speed > 0.0:
            if self._state != self.RUNNING:
                self.add_event(self.RUNNING)
                self._state = self.RUNNING
                _logger.info(f"Engine {self._id} is starting")
                self._start_time = datetime.datetime.now()
        elif speed == 0.0:
            if self._state == self.RUNNING:
                self._stop_time = datetime.datetime.now()
                self.add_event(self.ON)
                self._state = self.ON
                _logger.info(f"Engine {self._id} stops")
            elif self._state == self.OFF:
                _logger.info(f"Engine {self._id} is turned on")
                self.add_event(self.ON)
                self._state = self.ON
        self._speed = speed

    def new_message(self):
        self._last_message = time.time()

    def add_event(self, current_state):
        _logger.info(f"Engine {self._id} new event:({self._state},{current_state})")
        self._day_events.append(
            EngineEvent(self._total_hours, self._state, current_state)
        )

    def get_events(self):
        for e in self._day_events:
            yield e

    def get_events_pb(self):
        for e in self._day_events:
            e_pb = e.as_protobuf(self._id)
            # e_pb.engine_id = self._id
            yield e_pb

    def update_data(self, msg):
        if self._state == self.OFF:
            self.add_event(self.ON)
            self._state = self.ON
            _logger.info(f"Engine {self._id} is turned on. Total hours: {msg.total_engine_hours}")
        self._temperature = msg.temperature
        self._alternator_voltage = msg.alternator_voltage
        self._total_hours = msg.total_engine_hours

    def get_data(self, response: engine_data):
        response.engine_id = self._id
        response.state = self._state
        response.total_hours = self._total_hours
        response.speed = self._speed
        response.temperature = self._temperature
        response.alternator_voltage = self._alternator_voltage
        if self._start_time is not None:
            response.last_start_time = self._start_time.isoformat()
        if self._stop_time is not None:
            response.last_stop_time = self._stop_time.isoformat()

    def check_off(self):
        if self._state == self.OFF:
            return True
        if time.time() - self._last_message > 30.0:
            _logger.info(f"Engine {self._id} is turned off")
            if self._state == self.RUNNING:
                self._stop_time = datetime.datetime.now()
            self.add_event(self.OFF)
            self._state = self.OFF
            self._speed = 0.0
            self._temperature = 0.0
            return True
        return False





