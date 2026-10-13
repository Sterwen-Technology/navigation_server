#-------------------------------------------------------------------------------
# Name:        energy_simulator_service.py
# Purpose:     Energy Simulator gRPC service
#              Implements the EnergySimulator service defined in energy_simulator.proto
#              Receives simulated values from the EnergySimulator server and injects them
#              into the EnergyService process
#
# Author:      Vibe Code
#
# Created:     05/10/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time

from navigation_server.generated.energy_simulator_pb2 import simulator_parameter
from navigation_server.generated.energy_simulator_pb2_grpc import (
    EnergySimulatorServicer, add_EnergySimulatorServicer_to_server
)
from navigation_server.generated.energy_pb2 import energy_command_response, EnergySource
from navigation_server.router_common import GrpcService, resolve_ref, NavGenericMsg, TRANSPARENT_MSG
from navigation_server.couplers import VEDirectMsg, VED_TEXT


_logger = logging.getLogger("ShipDataServer." + __name__)


class EnergySimulatorServicerImpl(EnergySimulatorServicer):
    """
    gRPC servicer for EnergySimulator service

    Receives simulated data via gRPC and injects it into the energy management system
    by calling the publish methods of the corresponding devices
    """
    
    def __init__(self, name, opts):
        """
        Initialize the Energy Simulator servicer

        Args:
            name: Service name
            opts: Configuration options
        """
        self._name = name

        # Device service names - support single or multiple instances
        self._battery_service_name = opts.get('battery_service', str, None)
        
        # Support both mppt_service (single) and mppt_services (list) for backward compatibility
        mppt_single = opts.get('mppt_service', str, None)
        self._mppt_service_names = opts.getlist('mppt_services', str, [])
        if mppt_single:
            self._mppt_service_names = [mppt_single] if mppt_single not in self._mppt_service_names else self._mppt_service_names
        
        # Support both dc_dc_service (single) and dc_dc_services (list) for backward compatibility
        dc_dc_single = opts.get('dc_dc_service', str, None)
        self._dc_dc_service_names = opts.getlist('dc_dc_services', str, [])
        if dc_dc_single:
            self._dc_dc_service_names = [dc_dc_single] if dc_dc_single not in self._dc_dc_service_names else self._dc_dc_service_names
        
        self._energy_controller_name = opts.get('energy_controller', str, None)

        self._battery_service = None
        self._mppt_services = {}  # instance -> service
        self._dc_dc_services = {}  # instance -> service
        self._energy_controller = None

    def finalize(self):
        """Resolve all service references"""
        # Resolve battery service (single instance)
        if self._battery_service_name:
            try:
                self._battery_service = resolve_ref(self._battery_service_name)
                _logger.info(f"{self._name} connected to battery service: {self._battery_service_name}")
            except KeyError:
                _logger.warning(f"{self._name} battery service not found: {self._battery_service_name}")

        # Resolve MPPT services (multiple instances)
        for mppt_name in self._mppt_service_names:
            try:
                service = resolve_ref(mppt_name)
                instance = getattr(service.device, 'instance', 0) if hasattr(service, 'device') else 0
                self._mppt_services[instance] = service
                _logger.info(f"{self._name} connected to MPPT service: {mppt_name} (instance {instance})")
            except KeyError:
                _logger.warning(f"{self._name} MPPT service not found: {mppt_name}")
            except Exception as e:
                _logger.warning(f"{self._name} error resolving MPPT service {mppt_name}: {e}")

        # Resolve DC-DC charger services (multiple instances)
        for dc_dc_name in self._dc_dc_service_names:
            try:
                service = resolve_ref(dc_dc_name)
                instance = getattr(service.device, 'instance', 0) if hasattr(service, 'device') else 0
                self._dc_dc_services[instance] = service
                _logger.info(f"{self._name} connected to DC-DC service: {dc_dc_name} (instance {instance})")
            except KeyError:
                _logger.warning(f"{self._name} DC-DC service not found: {dc_dc_name}")
            except Exception as e:
                _logger.warning(f"{self._name} error resolving DC-DC service {dc_dc_name}: {e}")

        # Resolve energy controller
        if self._energy_controller_name:
            try:
                self._energy_controller = resolve_ref(self._energy_controller_name)
                _logger.info(f"{self._name} connected to energy controller: {self._energy_controller_name}")
            except KeyError:
                _logger.warning(f"{self._name} energy controller not found: {self._energy_controller_name}")

    
    def SimulateBattery(self, request, context):
        """
        Receive battery simulated data from the simulator server
        FOR_AGENT: BatteryService expects TWO messages in sequence:
        - Message 1: V, I, P, SOC, CE, TTG, VS, Alarm (dynamic data)
        - Message 2: H1, H2, H4, H6, H7, H8, H9, H10 (static/config data)
        """
        _logger.debug("gRPC request EnergySimulator.SimulateBattery")

        if self._battery_service:
            # Message 1: Dynamic data
            msg1_data = {
                'V': request.voltage * 1000,  # Voltage in mV
                'VS': 0.0,  # Auxiliary voltage in mV
                'I': request.current * 1000,  # Current in mA (positive = charging)
                'P': request.power,  # Power in W
                'CE': 0.0,  # Consumed Ah in mAh
                'SOC': request.state_of_charge * 1000,  # SoC in 0.01%
                'TTG': 0.0,  # Time to go in minutes
                'Alarm': 0,  # No alarm
                'PID': 'Simulated',  # Product ID
                'FW': '1.0',  # Firmware
                'BMV': 'Simulated Battery'  # Model
            }
            msg1 = VEDirectMsg(msg1_data, msg_type=VED_TEXT)
            self._battery_service.device.publish(msg1)
            
            # Message 2: Static configuration data (required fields: H1)
            msg2_data = {
                'H1': 10.0 * 1000,  # Deepest discharge in mV
                'H2': 10.0 * 1000,  # Last discharge in mV
                'H4': 0,  # Charge cycles
                'H6': 200.0 * 1000,  # Total Ah in mAh
                'H7': request.voltage * 1000,  # Min voltage in mV
                'H8': request.voltage * 1000,  # Max voltage in mV
                'H9': 10.5 * 1000,  # Last discharge voltage in mV
                'H10': request.voltage * 1000,  # Charge voltage in mV
                'PID': 'Simulated',
                'FW': '1.0'
            }
            msg2 = VEDirectMsg(msg2_data, msg_type=VED_TEXT)
            self._battery_service.device.publish(msg2)
        _logger.info(f"Simulating Battery:{request.voltage}V/{request.current}A soc={request.state_of_charge}")
        response = energy_command_response()
        response.id = 0
        response.command = "SimulateBattery"
        response.response = "OK"
        return response
    
    def SimulateMPPT(self, request, context):
        """
        Receive MPPT simulated data from the simulator server
        FOR_AGENT: Direct dictionary extraction from protobuf and publish to service
        """
        _logger.debug(f"gRPC request EnergySimulator.SimulateMPPT for instance {request.instance}")
        
        # FOR_AGENT: Create dictionary directly from protobuf request
        # MPPT data in Victron VE.Direct format
        data = {
            'PID': 'Simulated',  # Product ID
            'FW': '1.0',  # Firmware
            'SER#': f'SIM{request.instance:03d}',  # Serial number
            'V': request.output_voltage * 1000,  # Output voltage in mV
            'I': request.output_current * 1000,  # Output current in mA
            'VPV': request.panel_voltage * 1000,  # Panel voltage in mV
            'PPV': request.panel_power,  # Panel power in W
            'CS': 5,  # State (5 = Float)
            'ERR': 0,  # No error
            'MPPT': 2,  # MPPT state (2 = Active)
            'H21': 0.0,  # Day max power
            'H20': 0.0   # Day power
        }
        _logger.info(f"Simulating MPPT Output:{request.output_voltage}V/{request.output_current}A")
        response = energy_command_response()
        response.id = request.instance
        mppt_service = self._mppt_services.get(request.instance)
        if mppt_service:
            msg = VEDirectMsg(data, msg_type=VED_TEXT)
            mppt_service.device.publish(msg)
            response.command = "SimulateMPPT"
            response.response = "OK"
        else:
            _logger.warning(f"{self._name} MPPT instance {request.instance} not configured")
            response.command = "Missing MPPT"
            response.response = "ERROR"

        return response
    
    def SimulateDcDc(self, request, context):
        """
        Receive DC-DC charger simulated data from the simulator server
        FOR_AGENT: Direct dictionary extraction from protobuf and publish to service
        """
        _logger.debug(f"gRPC request EnergySimulator.SimulateDcDc for instance {request.instance}")
        
        # FOR_AGENT: Create dictionary in Victron Orion XS VE.Direct format
        # DC_DCData.process_msg expects:
        # - Input: DC_IN_V (0.01 V units), DC_IN_I (0.1 A units), DC_IN_P (W)
        # - Output: V (0.001 V units), I (0.001 A units), P (W)
        # - Device: PID, FWE, SER#, CS, ERR, OR, T, MODE
        data = {
            # Input side
            'DC_IN_V': request.input_voltage * 100,  # Convert V to 0.01 V units (24.0V -> 2400)
            'DC_IN_I': request.input_current * 10,    # Convert A to 0.1 A units (5.0A -> 50)
            'DC_IN_P': request.input_voltage * request.input_current,  # Input power in W
            # Output side
            'V': request.output_voltage * 1000,  # Output voltage in mV
            'I': request.output_current * 1000,  # Output current in mA
            'P': request.output_voltage * request.output_current,  # Output power in W (V * I)
            # Device information
            'PID': 'Simulated',  # Product ID
            'FWE': '1.0',  # Firmware (note: dc_dc_service uses 'FWE', not 'FW')
            'SER#': f'SIM{request.instance:03d}',  # Serial number
            'CS': 5,  # State (5 = Float)
            'ERR': 0,  # No error
            'OR': '0',  # No off reason (must be string for hex parsing in process_msg)
            'T': 250,  # Temperature 25.0°C (stored as 0.1°C)
            'MODE': 0  # Mode
        }
        _logger.info(f"Simulating DC-DC Output:{request.output_voltage}V/{request.output_current}A")
        response = energy_command_response()
        response.id = request.instance
        dc_dc_service = self._dc_dc_services.get(request.instance)
        if dc_dc_service:
            msg = VEDirectMsg(data, msg_type=VED_TEXT)
            dc_dc_service.device.publish(msg)
            response.command = "SimulateDcDc"
            response.response = "OK"
        else:
            _logger.warning(f"{self._name} DC-DC instance {request.instance} not configured")
            response.command = "Missing DcDc"
            response.response = "ERROR"
        return response


class EnergySimulatorService(GrpcService):
    """
    gRPC service for EnergySimulator
    
    This service is added to the EnergyService process to receive simulated values
    from the EnergySimulator server and inject them into the energy devices
    """
    
    def __init__(self, opts):
        super().__init__(opts)
        self._servicer = EnergySimulatorServicerImpl(self.name, opts)

    def finalize(self):
        """Finalize the service - register gRPC servicer and resolve services"""
        super().finalize('EnergySimulator', 'EnergySimulatorService')
        self._servicer.finalize()
        add_EnergySimulatorServicer_to_server(
            self._servicer,
            self.grpc_server
        )
        _logger.info("EnergySimulator service finalized and ready")
