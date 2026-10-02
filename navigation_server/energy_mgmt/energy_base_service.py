#-------------------------------------------------------------------------------
# Name:        energy_base_service
# Purpose:     Base class for energy management services (MPPT, Battery, EnergyController)
#              Incorporates common functionalities
#
# Author:      Laurent Carré
#
# Created:     23/09/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time
from collections import deque

from navigation_server.router_common import (GrpcService, resolve_ref, copy_protobuf_data,
                                             fill_protobuf_from_dict)
from navigation_server.router_core import NMEA0183Sentences
from navigation_server.generated.energy_pb2 import EnergySource

_logger = logging.getLogger("ShipDataServer." + __name__)


class EnergyDevice:
    """
    Base class for energy devices (MPPT, Battery, etc.)
    Provides common functionality for device management, trend tracking, and publishing
    """

    # Subclasses should override this with their EnergySource type
    energy_source_type = None  # Should be set to EnergySource enum value

    def __init__(self, opts, service):
        """
        Initialize common device parameters
        
        Args:
            opts: Configuration options dictionary
            service: The parent service instance
        """
        # Device identification
        self._name = opts.get('name', str, 'EnergyDevice')
        self._coupler_name = opts.get('coupler', str, None)
        if self._coupler_name is None:
            _logger.error("The energy device must be linked with a coupler")
            raise ValueError("coupler is required")
        self._coupler = None
        self._instance = opts.get('instance', int, 0)
        
        # Coupler timeout
        self._coupler_timeout = opts.get('coupler_timeout', float, 20.0)
        
        # Publisher configuration
        self._publisher_name = opts.get('publisher', str, None)
        if self._publisher_name is not None:
            self._protocol = opts.get_choice('protocol', ('nmea0183', 'nmea2000'), 'nmea0183')
            if self._protocol == 'nmea0183':
                NMEA0183Sentences.set_talker(opts.get('talker', str, 'ST'))
        self._publisher = None
        self._publish_function = None
        self._sid = 0  # Sequence ID for NMEA2000 messages
        
        # Service reference
        self._service = service
        
        # Data storage
        self._current_data = None
        self._current_data_dict = None
        
        # Trend tracking configuration
        trend_duration = opts.get('trend_duration', int, 5)  # minutes
        self._trend_period = opts.get('trend_interval', float, 10.0)  # seconds
        self._trend_depth = int((trend_duration * 60.) / self._trend_period)
        self._trend_buckets = deque(maxlen=self._trend_depth)
        
        # Device metadata
        self._device_label = opts.get('device_label', str, self._name)
        self._device_model = opts.get('device_model', str, 'Unknown')
        
        # Parameters dictionary (to be overridden by subclasses)
        self._parameters = {}
        
        # Communication and timing
        self._start_period = 0.0
        self._last_msg_ts = time.monotonic()
        self._communication_ok = False
        
        # Energy controller link (for devices that report to energy controller)
        self._energy_controller_name = opts.get('energy_controller', str, None)
        self._energy_controller = None

    @property
    def instance(self):
        """Get the device instance ID"""
        return self._instance

    @property
    def device_type(self):
        """
        Get the energy source type for this device
        Returns the EnergySource enum value
        """
        raise NotImplementedError("Subclasses must implement this method")

    @property
    def device_label(self):
        """Get the device label"""
        return self._device_label

    def stop_service(self):
        """Request to stop the service"""
        _logger.info(f"{self._name} request to stop service")
        self._service.stop_service()

    @property
    def trend_interval(self):
        """Get the trend interval in seconds"""
        return self._trend_period

    def get_trend_buckets(self):
        """Generator to yield trend buckets"""
        for b in self._trend_buckets:
            yield b

    def start(self):
        """
        Start the device - resolve references and register with coupler
        To be overridden by subclasses for additional initialization
        """
        # Resolve coupler reference
        try:
            self._coupler = resolve_ref(self._coupler_name)
        except KeyError:
            _logger.error(f"{self._name} missing coupler: {self._coupler_name}")
            self.stop_service()
            return
        
        # Attach to energy controller if configured
        if self._energy_controller_name is not None:
            try:

                service = resolve_ref(self._energy_controller_name)
                self._energy_controller = service.controller()
                assert self._energy_controller is not None
                self._energy_controller.register(self)
            except KeyError:
                _logger.warning(f"{self._name} missing energy controller: {self._energy_controller_name}")
        
        # Setup publisher if configured
        if self._publisher_name is not None:
            try:
                self._publisher = resolve_ref(self._publisher_name)
            except KeyError:
                _logger.error(f"{self._name} no publisher {self._publisher_name}")

            if self._publisher is not None:
                _logger.debug(
                    f"{self._name} publisher set: {self._publisher.object_name()} protocol: {self._protocol}")
                if self._protocol == 'nmea0183':
                    self._publish_function = self.publish0183
                else:
                    self._publish_function = self.publish2000
        
        # Register with coupler
        self._coupler.register(self)
        self._start_period = time.monotonic()

    def publish(self, msg):
        # Default implementation for devices that don't need special processing
        raise NotImplementedError("Subclasses must implement this method")

    def get_device_info(self, device_info):
        # fill the protobuf with device information
        if time.monotonic() - self._last_msg_ts < self._coupler_timeout :
            device_info.communication_ok = True
            if self._current_data is not None:
                self._current_data.output_info_pb(device_info)
        else:
            device_info.communication_ok = False
            self._communication_ok = False
            if self._energy_controller is not None:
                self._energy_controller.set_off_state(self._instance, self.device_type, False, False)
        device_info.device_label = self._device_label
        device_info.device_model = self._device_model
        device_info.instance = self._instance

    def get_device_parameters(self, device_parameters):
        """
        Fill device parameters protobuf
        """
        fill_protobuf_from_dict(device_parameters, self._parameters)

    def publish0183(self):
        """
        Publish data in NMEA0183 format - to be overridden by subclasses
        """
        _logger.debug(f"{self._name} publish NMEA0183")

    def publish2000(self):
        """
        Publish data in NMEA2000 format - to be overridden by subclasses
        """
        _logger.debug(f"{self._name} publish NMEA2000")

    def object_name(self):
        """For debug only - to be overridden by subclasses"""
        return self._name
