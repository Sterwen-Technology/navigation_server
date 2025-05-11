# -------------------------------------------------------------------------------
# Name:        NMEA2K-controller
# Purpose:     Analyse and process NMEA2000 network control messages with CAN access
#
# Author:      Laurent Carré
#
# Created:     02/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import threading

from navigation_server.router_core import NMEA2000Msg
from navigation_server.nmea2000 import NMEA2KController
from .nmea2k_application import NMEA2000Application, NMEA2000ApplicationPool
from .nmea2k_can_interface import SocketCANInterface, SocketCanError
from navigation_server.router_common import ObjectCreationError, set_global_var

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2KActiveController(NMEA2KController):

    def __init__(self, opts):

        super().__init__(opts)
        self._channel = opts.get('channel', str, 'can0')
        self._trace = opts.get('trace', bool, False)
        try:
            self._can = SocketCANInterface(self._channel, self._input_queue, self._trace)
        except SocketCanError as e:
            _logger.error(e)
            raise ObjectCreationError(str(e))
        self._coupler_queue = None
        self._applications = []
        self._app_index = {}
        self._apool = NMEA2000ApplicationPool(self, opts)
        self._application_names = opts.getlist('applications', str, None)
        self._address_change_request = None
        self._start_application_lock = threading.Lock()
        self._pgn_vector = {}
        self._app_timer = None
        self._timer_vector = []
        self._catch_all = []
        set_global_var("NMEA2K_ECU", self)

    @property
    def min_queue_size(self):
        return 60

    @property
    def channel(self) -> str:
        return self._channel

    def start(self):
        _logger.info("CAN active controller start")
        if self._application_names is not None:
            for ap_name in self._application_names:
                ap = self.resolve_direct_ref(ap_name)
                if ap is not None:
                    _logger.info("CAN active controller adding application:%s" % ap_name)
                    if issubclass(ap.__class__, NMEA2000Application):
                        ap.set_controller(self)
                        self.add_application(ap)
                    else:
                        _logger.error("Invalid application for CAN Controller (ECU) => ignored")
                else:
                    _logger.error("CAN active controller cannot find application %s" % ap_name)

        if len(self._applications) == 0:
            _logger.info("Creating default application")
            self.add_application(NMEA2000Application(self))

        _logger.debug("Starting CAN bus")
        self._can.start()
        super().start()
        self.start_applications()
        # start timer
        self._app_timer = threading.Timer(1.0, self._timer_lapse)
        self._app_timer.start()

    def _timer_lapse(self):
        _logger.debug("Active Controller entering timer scheduling with %d apps" % len(self._timer_vector))
        # self._start_application_lock.acquire()
        for app in self._timer_vector:
            app.wake_up()
        # self._start_application_lock.release()
        self._app_timer = threading.Timer(1.0, self._timer_lapse)
        self._app_timer.start()

    def timer_subscribe(self, application):
        _logger.debug("ActiveController timer subscribe:%s" % application.name)
        # self._start_application_lock.acquire()
        self._timer_vector.append(application)
        # self._start_application_lock.release()

    def timer_unsubscribe(self, application):
        # self._start_application_lock.acquire()
        self._timer_vector.remove(application)
        # self._start_application_lock.release()

    def stop(self):
        if self._timer_vector is not None:
            self._app_timer.cancel()
        # stop all applications first
        for app in self._applications:
            app.stop_request()
        self._can.stop()
        super().stop()

    @property
    def CAN_interface(self):
        return self._can

    @property
    def app_pool(self) -> NMEA2000ApplicationPool:
        return self._apool

    def set_pgn_vector(self, application, pgn_list):
        if type(pgn_list) is list:
            for pgn in pgn_list:
                if pgn in self._pgn_vector:
                    _logger.error(f"Duplicate vector for PGN {pgn} ignored")
                    continue
                self._pgn_vector[pgn] = application
        elif type(pgn_list) is int:
            if pgn_list == -1:
                self._catch_all.append(application)
            elif 254 > pgn_list >= 0:
                self._pgn_vector[pgn_list] = application

    def add_application(self, application):
        self._applications.append(application)
        self.add_application_index(application)

    def add_application_index(self, application):
        self._devices[application.address] = application
        self._app_index[application.address] = application
        self._can.add_address(application.address)

    def apply_change_application_address(self):
        # application must already be initialized with the target address
        self.remove_application_index(self._address_change_request[1])
        self.add_application_index(self._address_change_request[0])
        self._address_change_request = None

    def change_application_address(self, application, old_address):
        assert self._address_change_request is None
        self._address_change_request = (application, old_address)

    def remove_application_index(self, old_address: int):
        self.delete_device(old_address)
        self._can.remove_address(old_address)
        del self._app_index[old_address]

    def start_applications(self):
        _logger.debug("NMEA2000 Controller => Applications starts")
        for app in self._applications:
            # to limit the load on the CAN bus, applications are started one at a time
            _logger.debug("Start application %d" % app.id)
            if not self._start_application_lock.acquire(timeout=2.0):
                _logger.error("ActiveController timeout on application start")
            app.start_application()

    def application_started(self, application):
        try:
            _logger.debug("Application %d started" % application.id)
            self._start_application_lock.release()
        except RuntimeError:
            _logger.error("Active Controller => release before lock for application:%d" % application.id)

    def process_msg(self, msg: NMEA2000Msg):
        _logger.debug("CAN data received sa=%d PGN=%d da=%d" % (msg.sa, msg.pgn, msg.da))
        if msg.da != 255:
            # we have a da, so call the application
            try:
                if msg.is_iso_protocol:
                    self._app_index[msg.da].receive_msg(msg)
                else:
                    self._app_index[msg.da].receive_data_msg(msg)
            except KeyError:
                _logger.error("Wrongly routed message for destination %d pgn %d" % (msg.da, msg.pgn))
                return
        else:
            if msg.is_iso_protocol:
                super().process_msg(msg)    # proxy treatment
                # need also to process broadcast (DA=255) messages
                for application in self._applications:
                    application.receive_iso_msg(msg)
                if self._address_change_request is not None:
                    # address change cannot be applied on the fly
                    self.apply_change_application_address()
            else:
                _logger.debug("Active controller message dispatch sa=%d pgn =%d" % (msg.sa, msg.pgn))
                # new version 2024-09-11 dispatch via subscription
                try:
                    self._pgn_vector[msg.pgn].receive_data_msg(msg)
                except KeyError:
                    pass
                for application in self._catch_all:
                    application.receive_data_msg(msg)

    def poll_devices(self):
        """
        We just use the application 0 that is the default
        """
        app = self._applications[0] # shall not crash as we always have 1 app
        # app.send_iso_request(255, 126996)
        # app.send_iso_request(255, 126998)
        app.send_address_claim()

