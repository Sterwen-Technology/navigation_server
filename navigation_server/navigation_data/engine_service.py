#-------------------------------------------------------------------------------
# Name:        configuration
# Purpose:     Decode Yaml configuration file and manage the related objects
#
# Author:      Laurent Carré
#
# Created:     08/01/2022 - new version with features 20/03/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import threading
import datetime
import time
import os
import json

from navigation_server.router_common import MessageServerGlobals
from navigation_server.generated.navigation_data_pb2 import engine_data, engine_request, engine_response, engine_event
from navigation_server.generated.navigation_data_pb2_grpc import EngineDataServicer, add_EngineDataServicer_to_server

from navigation_server.router_common import GrpcSecondaryService

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
        # check and create root directory for engine
        self._root_dir = os.path.join(MessageServerGlobals.data_dir, 'engines')
        if not os.path.exists(self._root_dir):
            os.mkdir(self._root_dir)
        else:
            # check if we have already created engines
            engine_dirs = os.listdir(self._root_dir)
            for engine_dir in engine_dirs:
                _logger.info("Found %s directory" % engine_dir)
                engine_id_idx = engine_dir.find('#')
                if engine_id_idx >= 0:
                    # ok crate for existing dir
                    engine_id = int(engine_dir[engine_id_idx+1:])
                    try:
                        engine_object = EngineData(engine_id, self._root_dir, engine_dir)
                    except (IOError, json.JSONDecodeError) as err:
                        # we have a mangled repo => remove it
                        _logger.error(f"Mangled engine storage {err} in {self._root_dir}/{engine_dir} -> please correct")
                        continue
                    self._engines[engine_id] = engine_object

    def finalize(self):
        super().finalize()
        self._servicer = EngineDataServicerImpl(self)
        # now set up the subscriptions
        self._primary_service.subscribe(self, 127488, self.p127488)
        self._primary_service.subscribe(self, 127489, self.p127489)
        add_EngineDataServicer_to_server(self._servicer, self.grpc_server)
        self._timer.start()

    def get_engine(self, engine_id: int):
        try:
            return self._engines[engine_id]
        except KeyError:
            engine = EngineData(engine_id, self._root_dir)
            self._engines[engine_id] = engine
            return engine

    def check_off_engines(self):
        nb_engines = len(self._engines)
        for e in self._engines.values():
            e.save_status()
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

    def stop_service(self):
        if self._timer is not None:
            self._timer.cancel()
        super().stop_service()


class EngineEvent:

    def __init__(self, total_hours, previous_state, current_state, ts:datetime.datetime = None):
        if ts is None:
            self._ts = datetime.datetime.now()
        else:
            self._ts = ts
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

    def as_dict(self):
        return {
            'ts': self._ts.isoformat(),
            'total_hours': self._total_hours,
            'current_state': self._current_state,
            'previous_state': self._previous_state
        }


class EngineData:

    (OFF, ON, RUNNING) = range(0, 3)

    def __init__(self, engine_id:int, root_dir:str, engine_dir: str = None):
        self._id = engine_id
        self._root_dir = root_dir
        # self._status_file = os.path.join(root_dir, engine_dir, f'eng#{engine_id}-current_state')
        self._engine_dir = None
        self._current_date = None
        # self._event_file = os.path.join(root_dir, engine_dir, event_file)
        if engine_dir is None:
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
            self._engine_dir = f"engine#{engine_id}"
            try:
                os.mkdir(os.path.join(root_dir, self._engine_dir))
            except FileExistsError:
                pass

            self._status_file = os.path.join(root_dir, self._engine_dir, f'eng#{engine_id}-current_state')
            self.check_date()
        else:
            _logger.info("Reading data for engine %d" % engine_id)
            self._engine_dir = engine_dir
            # we read the data from the files
            self._status_file = os.path.join(root_dir, self._engine_dir, f'eng#{engine_id}-current_state')
            self.check_date()
            with open(self._status_file,'r') as fd:
                status = json.load(fd)
                last_save = datetime.datetime.fromisoformat(status['last_save'])
                self._state = status['state']
                self._speed = status['speed']
                self._first_on = datetime.datetime.fromisoformat(status['first_on'])
                if last_save.date() == self._current_date:
                    self._last_message = status['last_message']
                    self._temperature = status['temperature']
                    self._alternator_voltage = status['alternator_voltage']
                else:
                    self._last_message = 0.0
                    self._temperature = 0.
                    self._alternator_voltage = 0.

                self._total_hours = status['total_hours']
                start_time = status['start_time']
                if start_time is not None:
                    self._start_time = datetime.datetime.fromisoformat(start_time)
                else:
                    self._start_time = None
                stop_time = status['stop_time']
                if stop_time is not None:
                    self._stop_time = datetime.datetime.fromisoformat(stop_time)
                else:
                    self._stop_time = None
            self._day_events = []
            if os.path.exists(self._event_file):
                # ok we have events for today
                with open(self._event_file, 'r') as fd:
                    while True:
                        line = fd.readline()
                        if line:
                            event_r = json.loads(line)
                            self._day_events.append(
                                EngineEvent(event_r['total_hours'],
                                            event_r['previous_state'],
                                            event_r['current_state'],
                                            datetime.datetime.fromisoformat(event_r['ts']))
                            )
                        else:
                            break

    def check_date(self):
        actual_date = datetime.date.today()
        if self._current_date is None or actual_date != self._current_date:
            self._current_date = actual_date
            event_file = f"eng#{self._id}-events-{self._current_date.year}-{self._current_date.month}-{self._current_date.day}"
            self._event_file = os.path.join(self._root_dir, self._engine_dir, event_file)

    def as_dict(self):
        def json_date(date_d):
            if date_d is not None:
                return date_d.isoformat()
            else:
                return None

        return {
            'last_save': datetime.datetime.now().isoformat(),
            'state': self._state,
            'first_on': json_date(self._first_on),
            'last_message': self._last_message,
            'speed': self._speed,
            'total_hours': self._total_hours,
            'temperature': self._temperature,
            'alternator_voltage': self._alternator_voltage,
            'start_time': json_date(self._start_time),
            'stop_time': json_date(self._stop_time)
        }


    def update_speed(self, speed):
        if speed > 0.0:
            if self._state != self.RUNNING:
                self.add_event(self.RUNNING)
                # self._state = self.RUNNING
                _logger.info(f"Engine {self._id} is starting")
                self._start_time = datetime.datetime.now()
        elif speed == 0.0:
            if self._state == self.RUNNING:
                self._stop_time = datetime.datetime.now()
                self.add_event(self.ON)
                # self._state = self.ON
                _logger.info(f"Engine {self._id} stops")
            elif self._state == self.OFF:
                _logger.info(f"Engine {self._id} is turned on")
                self.add_event(self.ON)
                # self._state = self.ON
        self._speed = speed

    def new_message(self):
        self._last_message = time.time()

    def add_event(self, current_state):
        _logger.info(f"Engine {self._id} new event:({self._state},{current_state})")
        event = EngineEvent(self._total_hours, self._state, current_state)
        self._day_events.append( event )
        # now we save it
        self.check_date()
        with open(self._event_file,'a') as fd:
            line = json.dumps(event.as_dict())
            fd.write(line)
            fd.write('\n')
        self._state = current_state
        self.save_status()

    def save_status(self):
        with open(self._status_file, 'w') as fd:
            save_d = self.as_dict()
            json.dump(save_d, fd)

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





