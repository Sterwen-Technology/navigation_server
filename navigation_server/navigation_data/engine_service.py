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

from navigation_server.router_common import MessageServerGlobals, GrpcService, resolve_ref, fill_protobuf_from_dict
from navigation_server.generated.engine_data_pb2 import engine_data, engine_request, engine_response, engine_event, engine_run
from navigation_server.generated.engine_data_pb2_grpc import EngineDataServicer, add_EngineDataServicer_to_server
from navigation_server.generated.nmea2000_classes_gen import Pgn127488Class, Pgn127489Class


_logger = logging.getLogger("ShipDataServer."+__name__)


class EngineDataServicerImpl(EngineDataServicer):
    """
    Implementation of the EngineDataServicer interface.

    This class provides methods to interact with engine data and engine events.
    It acts as a bridge between higher-level services and the underlying engine
    service implementation. The main purpose of this class is to handle requests
    for engine data and events, process them with the help of the engine service,
    and return appropriate responses.

    Attributes:
        _engine_service: A reference to the engine service instance that provides
        core functionalities related to engine data and events. This is an
        internal dependency used to process the requests.

    Methods:
        GetEngineData(request, context):
            Handles requests to fetch engine data based on the provided engine ID.

        GetEngineEvents(request, context):
            Handles requests to fetch engine events based on the provided engine ID.
    """
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

    def GetEngineRuns(self, request, context):
        engine_id = request.engine_id
        response = engine_response()
        try:
            self._engine_service.get_engine_runs(engine_id, response.runs)
            response.error_message = "NO_ERROR"
        except KeyError:
            response.error_message = "NO_ENGINE"
        return response


class EngineDataService(GrpcService):
    """
    Manages engine-related data services and interactions between the system's components, particularly
    handling communication with engine data, events, and updates.

    This class tracks engine data, processes incoming messages, and organizes storage and retrieval
    of the engine information. It facilitates operations such as saving status, handling errors,
    updating engine parameters, and managing engine-specific events. It also ensures periodic
    checks for inactive engines and restarts timers accordingly.

    Attributes:
        _servicer: Initialized as None; later assigned an instance handling gRPC service.
        _engines: A dictionary mapping engine IDs to their corresponding EngineData objects.
        _timer: A threading.Timer object managing periodic engine checks.
        _root_dir: File path to the root directory used for engine data storage and management.
    """
    def __init__(self, opts):
        super().__init__(opts)
        self._servicer = None
        self._source = opts.get('source', str, None)
        if self._source is None:
            _logger.error("Engine data source not specified")
            raise ValueError("Engine data source not specified")
        self._source_function = None
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
        try:
            self._source_function = resolve_ref(self._source)
        except KeyError:
            _logger.error(f"Engine data source {self._source} not found")
            raise ValueError("Engine data source not found")
        # now set up the subscriptions
        self._source_function.subscribe(self, 127488, self.p127488, Pgn127488Class)
        self._source_function.subscribe(self, 127489, self.p127489, Pgn127489Class)
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
        engine.update_speed(msg)

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

    def get_engine_runs(self, engine_id, response):
        try:
            engine = self._engines[engine_id]
        except KeyError:
            _logger.error(f"Engine {engine_id} non existent")
            raise
        for run in engine.get_runs_pb():
            response.append(run)

    def stop_service(self):
        if self._timer is not None:
            self._timer.cancel()
        super().stop_service()


class EngineEvent:
    """
    Represents an engine event recording specific state transitions and related metadata.

    This class encapsulates the details of an engine event, such as the engine's
    previous state, current state, total operational hours, and an associated
    timestamp. It provides methods to convert the event data into different
    formats, including Protobuf and dictionary representations, to facilitate
    flexible integration with other parts of a system.
    """
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

def json_date(date_d):
    if date_d is not None:
        return date_d.isoformat()
    else:
        return None

class EngineData:
    """
    Represents the data and state management for an engine.

    This class is responsible for storing, managing, and updating the state of an engine.
    It handles the initialization of engine data, updating states, generating events,
    and persisting or loading engine-related data from files. This includes monitoring
    the engine's state transitions like turning off, running, or stopping, as well as
    storing performance metrics such as speed, temperature, and total running hours.

    Attributes:
    _id: int
        The unique identifier of the engine.
    _root_dir: str
        The root directory for engine data storage.
    _engine_dir: str
        The directory specific to the engine within the root directory.
    _status_file: str
        File path where the engine's current state is saved.
    _current_date: datetime.date
        The current date used to track daily events.
    _event_file: str
        File path to store daily engine events data.
    _state: int
        The current operational state of the engine (OFF, ON, or RUNNING).
    _speed: float
        Current speed of the engine.
    _first_on: datetime.datetime
        Timestamp when the engine was first turned ON.
    _last_message: float
        Timestamp of the last system message or update.
    _temperature: float
        Current operating temperature of the engine.
    _total_hours: float
        Total aggregate running hours of the engine.
    _alternator_voltage: float
        Alternator voltage of the engine.
    _start_time: datetime.datetime or None
        Timestamp when the engine was last started, None if not started.
    _stop_time: datetime.datetime or None
        Timestamp when the engine was last stopped, None if not stopped.
    _day_events: list
        List of EngineEvent objects representing daily engine events.
    """
    (OFF, ON, RUNNING) = range(0, 3)

    def __init__(self, engine_id:int, root_dir:str, engine_dir: str = None):
        """
        Initializes a new engine instance, setting up its directory structure, reading saved
        state data if available, and configuring engine-related properties based on the
        provided or default parameters.

        Attributes:
            _id (int): Identifier for the engine instance.
            _root_dir (str): Path to the root directory where engine data is stored.
            _engine_dir (str): Subdirectory for specific engine data or default path
                               if not provided.
            _status_file (str): Path to the status file for the engine's state.
            _current_date (datetime.date): Current date for engine operations.
            _event_file (str, optional): Path to the event file recording engine events.
            _state (str): Current operational state of the engine, default initialized
                          to 'OFF' if no engine directory is specified.
            _speed (float): Operational speed of the engine.
            _first_on (datetime.datetime): Timestamp of the first time the engine was started.
            _last_message (float): Timestamp of the last message or operational signal received.
            _temperature (float): Current operational temperature of the engine.
            _total_hours (float): The total hours the engine has been operational.
            _alternator_voltage (float): Current alternator voltage of the engine.
            _start_time (datetime.datetime, optional): Start time of the current operation cycle.
            _stop_time (datetime.datetime, optional): Stop time of the last operation cycle.
            _day_events (list): List of events recorded for the current day.

        Parameters:
            engine_id (int): Unique identifier for the engine.
            root_dir (str): The root directory for engine data storage.
            engine_dir: Optional[str]: The specific directory for engine data, defaulting
                                        to a generated directory name if not provided.
        """
        self._id = engine_id
        self._root_dir = root_dir
        # self._status_file = os.path.join(root_dir, engine_dir, f'eng#{engine_id}-current_state')
        self._engine_dir = None
        self._current_date = None
        self._event_file: str = None
        self._runs = []
        self._current_run = None
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
                current_run_dict = status.get('current_run', None)
                if current_run_dict is not None:
                    self._current_run = EngineRun(self._id, from_dict=current_run_dict)
                else:
                    self._current_run = None
                if self._state == self.RUNNING and self._current_run is None:
                    self._current_run = EngineRun(self._id, datetime.datetime.fromisoformat(status['start_time']), None)
                    self._runs.append(self._current_run)
            # reading events
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
            _logger.info(f"Engine data - creating new event file:{event_file}")
            self._event_file = os.path.join(self._root_dir, self._engine_dir, event_file)

    def as_dict(self):
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
            'stop_time': json_date(self._stop_time),
            'current_run': None if self._current_run is None else self._current_run.as_dict()
        }


    def update_speed(self, msg):
        speed = msg.engine_speed
        if speed > 0.0:
            if self._state != self.RUNNING:
                # self._state = self.RUNNING
                _logger.info(f"Engine {self._id} is starting")
                self._start_time = datetime.datetime.now()
                run = EngineRun(self._id, self._start_time, msg)
                self._runs.append(run)
                self._current_run = run
                self.add_event(self.RUNNING)
            else:
                if self._current_run is not None:
                    self._current_run.speed_input(msg)
                else:
                    _logger.error(f"Engine {self._id} speed input but no run is active")
        elif speed == 0.0:
            if self._state == self.RUNNING:
                self._stop_time = datetime.datetime.now()
                # self._state = self.ON
                _logger.info(f"Engine {self._id} stops")
                if self._current_run is not None:
                    self._current_run.stop_run()
                    _logger.info(f"Engine {self._id} run stopped: {json.dumps(self._current_run.as_dict())}")
                    self._current_run = None
                else:
                    _logger.error(f"Engine {self._id} run stopped but no run is active")
                self.add_event(self.ON)

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

    def get_runs_pb(self):
        for r in self._runs:
            yield r.as_protobuf()

    def update_data(self, msg):
        if self._state == self.OFF:
            self.add_event(self.ON)
            self._state = self.ON
            _logger.info(f"Engine {self._id} is turned on. Total hours: {msg.total_engine_hours}")
        self._temperature = msg.temperature
        self._alternator_voltage = msg.alternator_voltage
        self._total_hours = msg.total_engine_hours
        if self._current_run is not None:
            self._current_run.data_input(msg)

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
        if self._current_run is not None:
            self._current_run.as_protobuf(response.current_run)

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


class EngineRun:

    def __init__(self, engine_id:int, start_time:datetime.datetime = None, msg=None, from_dict:dict= None):
        self._engine_id = engine_id
        if from_dict is not None:
            self._start_time = datetime.datetime.fromisoformat(from_dict['start_time'])
            self._stop_time = datetime.datetime.fromisoformat(from_dict['stop_time'])
            self._total_hours_end = from_dict['total_hours_end']
            self._duration = from_dict['duration']
            self._max_temperature = from_dict['max_temperature']
            self._alternator_voltage = from_dict['alternator_voltage']
            self._last_msg_ts = from_dict['last_msg_ts']
            self._first_msg_ts = from_dict['first_msg_ts']
            self._average_speed = from_dict['average_speed']
        else:
            self._start_time = start_time
            self._stop_time = None
            self._total_hours_end = 0.0
            self._duration = 0.0
            self._max_temperature = 0.0
            self._alternator_voltage = 0.0
            self._last_msg_ts = time.monotonic()
            self._first_msg_ts = time.monotonic()
            if msg is not None:
                self._average_speed = msg.engine_speed
                self._max_speed = msg.engine_speed
            else:
                self._average_speed = 0.0
                self._max_speed = 0.0


    def speed_input(self, msg):
        speed = msg.engine_speed
        timestamp = time.monotonic()
        interval = timestamp - self._last_msg_ts
        accumulated_speed = self._average_speed * self._duration + speed * interval
        # print(speed,timestamp,interval,accumulated_speed,self._average_speed, self._duration)
        self._average_speed = accumulated_speed / (self._duration + interval)
        if speed > self._max_speed:
            self._max_speed = speed
        self._last_msg_ts = timestamp
        self._duration = timestamp - self._first_msg_ts


    def data_input(self, msg):
        self._max_temperature = max(self._max_temperature, msg.temperature)
        self._alternator_voltage = max(self._alternator_voltage, msg.alternator_voltage)
        self._total_hours_end = msg.total_engine_hours

    def stop_run(self):
        self._stop_time = datetime.datetime.now()

    def as_dict(self):
        return {
            'engine_id': self._engine_id,
            'start_time': self._start_time.isoformat(),
            'stop_time': json_date(self._stop_time),
            'total_hours': self._total_hours_end,
            'duration': self._duration,
            'average_speed': self._average_speed,
            'max_speed': self._max_speed,
            'max_temperature': self._max_temperature,
            'alternator_voltage': self._alternator_voltage
        }

    def as_protobuf(self) -> engine_run:
        fields = self.as_dict()
        run_pb = engine_run()
        fill_protobuf_from_dict(fields, run_pb)
        return run_pb