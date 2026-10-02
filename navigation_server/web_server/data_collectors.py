#-------------------------------------------------------------------------------
# Name:        data_collectors
# Purpose:     Data collection layer for the web server
#
#              This module provides the collector classes that communicate with
#              the navigation_server gRPC services to obtain data and display
#              parameters. It encapsulates the logic and data structuring to
#              respond to requests from the web server.
#
#              Architecture:
#              - NavigationSystemCollector: Top-level collector that handles all
#                requests and routes them to appropriate collectors
#              - ProcessCollector: Collects data about a specific process
#              - Service Collectors: One for each service type (Console, NMEA2000,
#                Engine, MPPT, Energy, Battery)
#
# Author:      Vibe Code
#
# Created:     25/09/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Type, Any

from navigation_server.router_common import GrpcClient, GrpcAccessException
from navigation_server.router_common.agent_interface import AgentClient
from navigation_server.router_common.global_variables import MessageServerGlobals
from navigation_server.navigation_clients import NetworkClient
from navigation_server.navigation_clients.console_client import ConsoleClient
from navigation_server.navigation_clients.n2k_can_client import NMEA2000CanClient
from navigation_server.navigation_clients.navigation_data_client import EngineClient
from navigation_server.navigation_clients.energy_client import MPPT_Client, EnergyServiceClient, BatteryServiceClient
from navigation_server.navigation_clients.gnss_client import GNSSClient
from navigation_server.generated.energy_pb2 import EnergyControllerData, EnergyControllerParameters, BatteryBank, battery_in_out, BatteryUnit, EnergySourceDevice, EnergySourceData
from navigation_server.generated.network_pb2 import NetInterface as NetInterfacePb

_logger = logging.getLogger("ShipDataServer." + __name__)


# Forward declarations for type hints
class NavigationSystemCollector:
    pass


class ProcessCollector:
    """Collects and manages data for a single process and its services.
    
    This class handles the gRPC connection to a specific process and provides
    access to its services. It caches the connection and manages service clients.
    
    Note: This was previously named ProcessBox in web_server_impl.py
    """
    
    def __init__(self, system_collector: 'NavigationSystemCollector', process_name: str, grpc_port: int, secure: bool):
        self._system_collector = system_collector
        self._process_name = process_name
        self._port = grpc_port
        self._secure = secure
        self._grpc_server = None
        self._service_collectors: Dict[str, 'BaseServiceCollector'] = {}  # service_type -> BaseServiceCollector instance
        self._services_definition = []  # List of Service descriptors from protobuf
        self._lock = threading.Lock()
    
    @property
    def process_name(self) -> str:
        """The name of the process this collector is managing."""
        return self._process_name
    
    @property
    def port(self) -> int:
        """The gRPC port for this process."""
        return self._port
    
    @property
    def secure(self) -> bool:
        """Whether this process uses secure gRPC."""
        return self._secure
    
    def get_grpc_server(self) -> GrpcClient:
        """Get or create the gRPC server connection for this process.
        
        Returns None if port is invalid (0) to allow graceful handling of
        processes that haven't fully initialized their gRPC server yet.
        """
        # Handle invalid port (e.g., 0 during process startup)
        if self._port <= 0:
            _logger.debug(f"Skipping gRPC server for process {self._process_name}: invalid port {self._port}")
            return None
            
        if self._grpc_server is None or self._grpc_server.not_connected:
            with self._lock:
                if self._grpc_server is None or self._grpc_server.not_connected:
                    server_key = f"{self._system_collector.agent_host}:{self.port}"
                    self._grpc_server = GrpcClient.get_client(server_key, secure=self.secure)
                    self._grpc_server.connect()
                    self._grpc_server.wait_connect(5.0)
                    # now retrieve all services from the server (process)
                    self._services_definition = self._grpc_server.send_control_channel_command("SERVICES")
        return self._grpc_server
    
    def get_service_collector(self, service_type: str, collector_class):
        """Get or create a service collector for this process.
        
        Args:
            service_type: The type of service (e.g., 'console', 'nmea2000', 'engine')
            collector_class: The BaseServiceCollector subclass to instantiate
            
        Returns:
            BaseServiceCollector instance for the requested service
        """
        if service_type not in self._service_collectors:
            # Resolve the gRPC server outside the service lock: get_grpc_server()
            # holds its own lock, so nesting it under self._lock would deadlock
            # (threading.Lock is not reentrant).
            grpc_server = self.get_grpc_server()
            with self._lock:
                if service_type not in self._service_collectors:
                    service = collector_class(self, grpc_server)
                    self._service_collectors[service_type] = service
        return self._service_collectors[service_type]

    @property
    def services(self) -> List:
        """The list of Service descriptors implemented by this process.

        Populated once when the process gRPC server is first connected via the
        control-channel SERVICES command, so callers can check which services a
        process exposes without re-querying the agent.
        """
        # If we haven't connected yet, services_definition will be empty
        # The first call to get_grpc_server() will populate it
        if not self._services_definition and self._grpc_server is None:
            self.get_grpc_server()
        return self._services_definition

    def has_service(self, rpc_service: str) -> bool:
        """Return True if this process implements the given gRPC service."""
        return any(svc.rpc_service == rpc_service for svc in self.services)
    
    @staticmethod
    def process_to_dict(proc, system_collector: 'NavigationSystemCollector') -> dict:
        """Convert a process descriptor to a dict.
        
        This handles the process-level data (id, name, state, ports, etc.) but not
        the server/console data which is handled by ConsoleServiceCollector.
        
        Args:
            proc: Process descriptor from NavigationSystemMsgProxy
            system_collector: The NavigationSystemCollector for accessing services
            
        Returns:
            Dictionary representation of the process
        """
        services_list = [
            {
                "service_name": service.service_name,
                "rpc_service": service.rpc_service,
            }
            for service in proc.services
        ]
        return {
            "id": proc.id,
            "name": proc.name,
            "state": proc.state,
            "grpc_port": proc.grpc_port,
            "secure_grpc": proc.secure_grpc,
            "console_present": proc.console_present,
            "status": proc.status,
            "error": proc.error,
            "version": proc.version,
            "start_time": proc.start_time,
            "hostname": proc.hostname,
            "pid": proc.pid,
            "purpose": proc.purpose,
            "settings": proc.settings,
            "is_systemd": proc.is_systemd,
            "display_order": proc.display_order if hasattr(proc, 'display_order') else 0,
            "hidden": proc.hidden if hasattr(proc, 'hidden') else False,
            "services": services_list,
        }
    
    def send_cmd(self, cmd: str) -> dict:
        """Send a command to this process via the agent."""
        if cmd not in ("start", "stop", "restart"):
            return {"ok": False, "error": f"Unsupported command: {cmd}"}
        system_collector = self._system_collector
        system_collector._connect()
        if system_collector._server.not_connected:
            return {"ok": False, "error": "Agent gRPC server unreachable"}
        resp = system_collector._agent.process_cmd(cmd, self._process_name)
        if resp is None:
            return {"ok": False, "error": f"Command '{cmd}' failed on {self._process_name}"}
        return {"ok": True, "response": resp.response}
    
    def close(self):
        """Clean up resources for this process collector."""
        if self._grpc_server:
            try:
                # Close the gRPC channel if the method exists
                if hasattr(self._grpc_server, 'close') and callable(self._grpc_server.close):
                    self._grpc_server.close()
                else:
                    # Manually cleanup the channel and services
                    if hasattr(self._grpc_server, '_channel') and self._grpc_server._channel is not None:
                        try:
                            self._grpc_server._channel.close()
                        except Exception as e:
                            _logger.warning(f"Error closing gRPC channel for {self._process_name}: {e}")
                    # Clear services and reset state
                    if hasattr(self._grpc_server, '_services'):
                        self._grpc_server._services.clear()
                    self._grpc_server._state = self._grpc_server.NOT_CONNECTED if hasattr(self._grpc_server, 'NOT_CONNECTED') else 0
            except Exception as e:
                _logger.warning(f"Error cleaning up gRPC server for {self._process_name}: {e}")
        self._grpc_server = None
        self._service_collectors.clear()
    
    @staticmethod
    def send_cmd_to_process(system_collector: 'NavigationSystemCollector', target: str, cmd: str) -> dict:
        """Send a command to a specific process."""
        process_collector = system_collector._get_process_collector(target)
        return process_collector.send_cmd(cmd)


class BaseServiceCollector(ABC):
    """Abstract base class for service collectors.
    
    Each service (Console, NMEA2000, Engine, etc.) has its own subclass that
    implements the specific data retrieval and formatting methods.
    
    Note: This was previously named ServiceWindow in web_server_impl.py
    """
    
    def __init__(self, process_collector: ProcessCollector, grpc_server: GrpcClient):
        self._process_collector = process_collector
        self._grpc_server = grpc_server
        self._client = None
        self._initialized = False
    
    @property
    def process_name(self) -> str:
        """The name of the process this service belongs to."""
        return self._process_collector.process_name
    
    @property
    def grpc_server(self) -> GrpcClient:
        """The gRPC server connection for this service."""
        return self._grpc_server
    
    def _ensure_client(self):
        """Ensure the gRPC client is initialized."""
        if not self._initialized:
            # Ensure grpc_server is connected before initializing client
            if self._grpc_server.not_connected:
                self._grpc_server.connect()
                self._grpc_server.wait_connect(5.0)
            self._initialize_client()
            self._initialized = True
    
    @abstractmethod
    def _initialize_client(self):
        """Initialize the gRPC client for this service."""
        pass
    
    @abstractmethod
    def get_data(self) -> dict:
        """Get the data for this service as a dictionary.
        
        Returns:
            Dictionary with service data, must include 'ok' key
        """
        pass


class ConsoleServiceCollector(BaseServiceCollector):
    """Service collector for Console service."""
    
    def _initialize_client(self):
        self._client = ConsoleClient()
        self._grpc_server.add_service(self._client)
    
    def get_data(self) -> dict:
        """Get console status data (servers + couplers)."""
        self._ensure_client()
        try:
            status = self._client.server_status()
            servers = []
            for srv in status.get_sub_servers():
                connections = [
                    {
                        "remote_ip": c.remote_ip,
                        "remote_port": c.remote_port,
                        "total_msg": c.total_msg,
                        "msg_rate": c.msg_rate,
                        "max_delay": c.max_delay,
                    }
                    for c in srv.connections
                ]
                servers.append({
                    "server_class": srv.server_class,
                    "name": srv.name,
                    "server_type": srv.server_type,
                    "running": srv.running,
                    "nb_connections": srv.nb_connections,
                    "port": srv.port,
                    "protocol": srv.protocol,
                    "connections": connections,
                })
            couplers = []
            try:
                for c in self._client.get_couplers():
                    couplers.append({
                        "name": c.name,
                        "coupler_class": c.coupler_class,
                        "state": c.state,
                        "dev_state": c.dev_state,
                        "protocol": c.protocol,
                        "msg_in": c.msg_in,
                        "msg_raw": c.msg_raw,
                        "msg_out": c.msg_out,
                        "status": c.status,
                        "error": c.error,
                        "input_rate": c.input_rate,
                        "input_rate_raw": c.input_rate_raw,
                        "output_rate": c.output_rate,
                        "trace_on": c.trace_on,
                    })
            except GrpcAccessException:
                pass
            return {
                "ok": True,
                "process": self.process_name,
                "grpc_port": self._grpc_server.address.rsplit(":", 1)[-1] if ":" in self._grpc_server.address else 0,
                "servers": servers,
                "couplers": couplers,
            }
        except GrpcAccessException:
            return {"ok": False, "error": "Console ServerStatus call failed"}
    
    def coupler_cmd(self, coupler_name: str, cmd: str) -> dict:
        """Send a command to a coupler."""
        allowed = ("start", "stop", "start_trace_raw", "stop_trace", "suspend", "resume")
        if cmd not in allowed:
            return {"ok": False, "error": f"Unsupported coupler command: {cmd}"}
        self._ensure_client()
        try:
            return {"ok": True, "result": self._client.coupler_cmd(coupler_name, cmd)}
        except GrpcAccessException:
            return {"ok": False, "error": "Coupler command failed"}
    
    def execute(self, parameters: list, **kwargs) -> dict:
        """Execute Console service commands.
        
        Commands:
        - No parameters or "status": get console status
        - coupler/{coupler_name}: send coupler command (needs cmd in kwargs)
        """
        if not parameters:
            return self.get_data()
        
        command = parameters[0]
        
        if command == "status":
            return self.get_data()
        elif command.startswith("coupler/"):
            # coupler/{coupler_name}
            parts = command.split("/", 1)
            if len(parts) == 2:
                coupler_name = parts[1]
                cmd = kwargs.get("cmd")
                if not cmd:
                    return {"ok": False, "error": "missing 'cmd' parameter for coupler command"}
                return self.coupler_cmd(coupler_name, cmd)
        
        return {"ok": False, "error": f"Unknown console command: {command}"}
    
    @staticmethod
    def get_console_status_for_process(system_collector: 'NavigationSystemCollector', process_name: str) -> dict:
        """Get console status for a specific process."""
        process_collector = system_collector._get_process_collector(process_name)
        service_collector = process_collector.get_service_collector('console', ConsoleServiceCollector)
        return service_collector.get_data()
    
    @staticmethod
    def send_coupler_cmd(system_collector: 'NavigationSystemCollector', process_name: str, coupler_name: str, cmd: str) -> dict:
        """Send coupler command for a specific process."""
        allowed = ("start", "stop", "start_trace_raw", "stop_trace", "suspend", "resume")
        if cmd not in allowed:
            return {"ok": False, "error": f"Unsupported coupler command: {cmd}"}
        process_collector = system_collector._get_process_collector(process_name)
        service_collector = process_collector.get_service_collector('console', ConsoleServiceCollector)
        return service_collector.coupler_cmd(coupler_name, cmd)
    
    @staticmethod
    def servers_to_dict(system_collector: 'NavigationSystemCollector', process_name: str, proc_servers) -> list:
        """Convert server descriptors from a process to a list of dicts.
        
        This handles the console/service server data for a process.
        
        Args:
            system_collector: The NavigationSystemCollector for accessing services
            process_name: Name of the process
            proc_servers: List of server descriptors from the process
            
        Returns:
            List of server dictionaries
        """
        servers = []
        for server in proc_servers:
            connections = [
                {
                    "remote_ip": c.remote_ip,
                    "remote_port": c.remote_port,
                    "total_msg": c.total_msg,
                    "msg_rate": c.msg_rate,
                    "max_delay": c.max_delay,
                }
                for c in server.connections
            ]
            servers.append({
                "server_class": server.server_class,
                "name": server.name,
                "server_type": server.server_type,
                "running": server.running,
                "nb_connections": server.nb_connections,
                "port": server.port,
                "protocol": server.protocol,
                "connections": connections,
            })
        return servers


class NMEA2000ServiceCollector(BaseServiceCollector):
    """Service collector for NMEA2000 service."""
    
    def _initialize_client(self):
        self._client = NMEA2000CanClient()
        self._grpc_server.add_service(self._client)
    
    def get_data(self) -> dict:
        """Get NMEA2000 status data."""
        self._ensure_client()
        try:
            status = self._client.get_status()
            devices = []
            for dev in status.devices:
                devices.append({
                    "address": dev.address,
                    "is_proxy": dev.is_proxy,
                    "manufacturer_name": dev.manufacturer_name,
                    "product_name": dev.product_name,
                })
            return {
                "ok": True,
                "process": self.process_name,
                "channel": status.channel,
                "status": status.status,
                "incoming_rate": status.incoming_rate,
                "outgoing_rate": status.outgoing_rate,
                "traces_on": status.traces_on,
                "devices": devices,
            }
        except GrpcAccessException:
            return {"ok": False, "error": "NMEA2000 GetStatus call failed"}
    
    def get_device(self, device_address: int) -> dict:
        """Get detailed info for a single NMEA2000 device."""
        self._ensure_client()
        try:
            dev = self._client.get_device(device_address)
            pgn_stats = []
            for stat in (dev.stats or []):
                pgn_stats.append({"pgn": stat.pgn, "count": stat.count, "direction": "in"})
            for stat in (dev.out_stats or []):
                pgn_stats.append({"pgn": stat.pgn, "count": stat.count, "direction": "out"})
            return {
                "ok": True,
                "address": dev.address,
                "is_proxy": dev.is_proxy,
                "manufacturer_name": dev.manufacturer_name,
                "product_name": dev.product_name,
                "pgn_stats": pgn_stats,
            }
        except GrpcAccessException:
            return {"ok": False, "error": "NMEA2000 GetDeviceStatus call failed"}
    
    def get_pgn_definition(self, pgn: int) -> dict:
        """Return the PGN definition (description) for a given PGN."""
        self._ensure_client()
        try:
            definition = self._client.get_pgn_definition(pgn)
            return {"ok": True, "pgn": pgn, "definition": definition}
        except GrpcAccessException:
            return {"ok": False, "error": "NMEA2000 GetPgnDefinition call failed"}
    
    def trace_cmd(self, cmd: str) -> dict:
        """Send a trace command to the NMEA2000 service."""
        self._ensure_client()
        if cmd not in ("start_trace", "stop_trace"):
            return {"ok": False, "error": f"Unsupported NMEA2000 command: {cmd}"}
        try:
            result = self._client.trace_cmd(cmd)
            return {"ok": True, "result": result}
        except GrpcAccessException:
            return {"ok": False, "error": "NMEA2000 trace command failed"}
    
    def device_cmd(self, address: int, cmd: str) -> dict:
        """Send a command to a NMEA2000 device."""
        self._ensure_client()
        try:
            return {"ok": True, "result": self._client.device_cmd(address, cmd)}
        except GrpcAccessException:
            return {"ok": False, "error": "Device command failed"}
    
    def execute(self, parameters: list, **kwargs) -> dict:
        """Execute NMEA2000 service commands.
        
        Commands:
        - No parameters or "status": get NMEA2000 status
        - device/{address}: get device info
        - pgn/{pgn}: get PGN definition
        - trace/{cmd}: send trace command (start_trace/stop_trace)
        - device_cmd: send device command
        """
        if not parameters:
            return self.get_data()
        
        command = parameters[0]
        
        if command == "status":
            return self.get_data()
        elif command.startswith("device/"):
            # device/{address}
            try:
                address = int(command.split("/", 1)[1])
                return self.get_device(address)
            except (ValueError, IndexError):
                return {"ok": False, "error": f"Invalid device address in command: {command}"}
        elif command.startswith("pgn/"):
            # pgn/{pgn}
            try:
                pgn = int(command.split("/", 1)[1])
                return self.get_pgn_definition(pgn)
            except (ValueError, IndexError):
                return {"ok": False, "error": f"Invalid PGN in command: {command}"}
        elif command.startswith("trace/"):
            # trace/{cmd}
            trace_cmd = command.split("/", 1)[1]
            return self.trace_cmd(trace_cmd)
        elif command == "device_cmd":
            # device_cmd with address and cmd in kwargs
            address = kwargs.get("address")
            cmd = kwargs.get("cmd")
            if address is None or cmd is None:
                return {"ok": False, "error": "missing 'address' or 'cmd' parameter"}
            return self.device_cmd(address, cmd)
        
        return {"ok": False, "error": f"Unknown NMEA2000 command: {command}"}


class EngineServiceCollector(BaseServiceCollector):
    """Service collector for the EngineData service.

    The collector caches the list of engine parameters (static engine definitions)
    retrieved once when the client is initialized, then serves both the engine
    list and the detailed engine data for each engine instance from that list.
    """
    
    def _initialize_client(self):
        self._client = EngineClient()
        self._grpc_server.add_service(self._client)
        # List of engine_parameters (static engine definitions) for this process.
        # Default to None before the call so that, if get_engines() raises, the
        # collector is left in a safe (empty) state rather than missing the attribute.
        self._engines = None
        self._engines = self._client.get_engines()
    
    @staticmethod
    def _parameters_dict(params) -> dict:
        if params is None:
            return {}
        return {
            "max_rpm": params.max_rpm,
            "voltage_scale": params.voltage_scale,
            "voltage_high_alert": params.voltage_high_alert,
            "voltage_low_alert": params.voltage_low_alert,
            "temperature_scale": params.temperature_scale,
            "temperature_high_alert": params.temperature_high_alert,
        }

    def _engine_summary(self, engine_id: int, params, data) -> dict:
        """Build the summary dict for one engine (used by engine_list)."""
        return {
            "id": engine_id,
            "label": params.label if params else "Engine",
            "model": params.model if params else "Unknown",
            "state": data.state,
            "speed": round(data._msg.speed, 0),
            "temperature": round(data._msg.temperature - 273.15, 0),  # Kelvin to Celsius
            "alternator_voltage": round(data._msg.alternator_voltage, 2),
            "total_hours": round(data._msg.total_hours / 3600.0, 1),  # Seconds to decimal hours
            "last_start_time": data.last_start_time,
            "last_stop_time": data.last_stop_time,
            "process": self.process_name,
            "parameters": self._parameters_dict(params),
        }

    def get_engine_list(self) -> list:
        """Return the list of engine summaries for this process.

        Iterates over the cached engine parameters and fetches the live data for
        each engine instance. Engines whose data cannot be retrieved are skipped.
        """
        self._ensure_client()
        engines = []
        for params in (self._engines or []):
            engine_id = params.engine_id
            try:
                data = self._client.get_data(engine_id)
            except GrpcAccessException:
                _logger.warning(f"Engine data call failed for {self.process_name} engine #{engine_id}")
                continue
            if data is None:
                continue
            engines.append(self._engine_summary(engine_id, params, data))
        return engines

    def get_engine_data(self, engine_id: int) -> dict:
        """Return detailed data (runtime + events + runs) for one engine instance."""
        self._ensure_client()
        try:
            data = self._client.get_data(engine_id)
            if data is None:
                return {"ok": False, "error": f"No engine data for instance #{engine_id}"}
            params = None
            for p in (self._engines or []):
                if p.engine_id == engine_id:
                    params = p
                    break
            events = self._client.get_events(engine_id)
            runs = self._client.get_runs(engine_id)
            current_run = data.current_run if data.current_run else None
            runs_list = []
            for r in (runs if runs else []):
                _logger.debug(
                    f"Engine {self.process_name} run #{r.start_time} "
                    f"raw protobuf duration={r._msg.duration} start={r.start_time} stop={r.stop_time}"
                )
                runs_list.append({
                    "start_time": r.start_time,
                    "stop_time": r.stop_time,
                    "total_hours": round(r.total_hours / 3600.0, 1),  # Seconds to hours, 1 decimal
                    "duration": r.duration ,  # No conversion here => front end
                    "average_speed": round(r.average_speed, 0),
                    "max_speed": round(r.max_speed, 0),
                    "max_temperature": round(r.max_temperature - 273.15, 0),  # Kelvin to Celsius
                    "alternator_voltage": round(r.alternator_voltage, 2),
                })
            return {
                "ok": True,
                "engine_id": engine_id,
                "label": params.label if params else "Engine",
                "model": params.model if params else "Unknown",
                "state": data.state,
                "speed": round(data._msg.speed, 0),
                "temperature": round(data._msg.temperature - 273.15, 0),  # Kelvin to Celsius
                "alternator_voltage": round(data._msg.alternator_voltage, 2),
                "total_hours": round(data._msg.total_hours / 3600.0, 1),  # Seconds to decimal hours
                "last_start_time": data.last_start_time,
                "last_stop_time": data.last_stop_time,
                "current_run": {
                    "start_time": current_run.start_time if current_run else None,
                    "stop_time": current_run.stop_time if current_run else None,
                    "total_hours": round(current_run.total_hours / 3600.0, 1) if current_run else 0,
                    "duration": current_run.duration if current_run else 0,  # Seconds to minutes, 2 decimal
                    "average_speed": round(current_run.average_speed, 0) if current_run else 0,
                    "max_speed": round(current_run.max_speed, 0) if current_run else 0,
                    "max_temperature": round(current_run.max_temperature - 273.15, 0) if current_run else 0,  # Kelvin to Celsius
                    "alternator_voltage": current_run.alternator_voltage if current_run else 0,
                } if current_run else None,
                "parameters": self._parameters_dict(params),
                "events": [{
                    "timestamp": e.timestamp,
                    "total_hours": round(e.total_hours / 3600.0 , 1),
                    "current_state": e.current_state,
                    "previous_state": e.previous_state,
                } for e in (events if events else [])],
                "runs": runs_list,
            }
        except GrpcAccessException:
            return {"ok": False, "error": "Engine data call failed"}

    def get_data(self) -> dict:
        """ServiceCollector contract: return the engine list for this process."""
        try:
            return {"ok": True, "engines": self.get_engine_list()}
        except GrpcAccessException:
            return {"ok": False, "error": "Engine service unavailable"}
    
    def execute(self, parameters: list, **kwargs) -> dict:
        """Execute Engine service commands.
        
        Commands:
        - No parameters or "status": get engine list
        - {engine_id}: get detailed engine data
        """
        if not parameters:
            return self.get_data()
        
        command = parameters[0]
        
        if command == "status":
            return self.get_data()
        else:
            # Try to parse as engine_id
            try:
                engine_id = int(command)
                return self.get_engine_data(engine_id)
            except ValueError:
                return {"ok": False, "error": f"Unknown engine command: {command}"}


class MPPTServiceCollector(BaseServiceCollector):
    """Service collector for the MPPT (solar charge controller) service.

    The collector exposes three facets of an MPPT device:
      * device info (semi-static: product id, firmware, serial, state, error,
        mppt_state, day_max_power, day_power) and its MPPT_parameters,
      * live output (panel_voltage, voltage, current, panel_power),
      * trailing power trend (repeated solar_output samples).

    All graphics ranges (bargraph maxima, trend window) are driven by the
    MPPT_parameters returned by the device, so the frontend scales itself to
    the configured panel_max_power / panel_max_voltage / max_voltage.
    """

    def _initialize_client(self):
        self._client = MPPT_Client()
        self._grpc_server.add_service(self._client)

    @staticmethod
    def _parameters_dict(params) -> dict:
        if params is None:
            return {}
        return {
            "instance": params.instance,
            "panel_max_power": round(params.panel_max_power, 1),
            "panel_max_voltage": round(params.panel_max_voltage, 1),
            "max_voltage": round(params.max_voltage, 1),
            "trend_duration": round(params.trend_duration, 1),
            "trend_interval": round(params.trend_interval, 1),
        }
    
    def get_data(self) -> dict:
        """Return device info + parameters + live output for this MPPT process.

        A single 'parameters' command is sent to GetDeviceInfo so the server
        returns the MPPT_parameters block alongside the semi-static device
        fields. GetOutput is queried independently for the live readings.
        """
        self._ensure_client()
        try:
            device = self._client.getDeviceInfo()
            output = self._client.getOutput()
            communication_ok = device.communication_ok
            if communication_ok:
                out = {
                    "panel_voltage": round(output.panel_voltage, 2),
                    "voltage": round(output.voltage, 2),
                    "current": round(output.current, 2),
                    "panel_power": round(output.panel_power, 1),
                }
            else:
                out = {
                    "panel_voltage": None,
                    "voltage": None,
                    "current": None,
                    "panel_power": None,
                }
            return {
                "ok": True,
                "process": self.process_name,
                "instance": device.instance,
                "communication_ok": communication_ok,
                "device_label": device.device_label,
                "device_model": device.device_model,
                "product_id": device.product_id,
                "firmware": device.firmware,
                "serial": device.serial,
                "error": device.error,
                "state": device.state,
                "mppt_state": device.mppt_state,
                "day_max_power": round(device.day_max_power, 1),
                "day_power": round(device.day_yield, 3),
                "msg_timestamp": device.msg_timestamp,
                "parameters": self._parameters_dict(device.parameters),
                "output": out,
            }
        except GrpcAccessException:
            return {"ok": False, "error": "MPPT service call failed"}

    def get_trend(self) -> dict:
        """Return the trailing solar output trend (panel power over time).

        The trend window (duration and sampling interval) is governed by the
        MPPT_parameters returned with the device info; the server decides how
        many samples to return.
        """
        self._ensure_client()
        try:
            trend = self._client.getTrend()
            values = []
            for v in (trend.values if trend else []):
                values.append({
                    "panel_voltage": round(v.panel_voltage, 2),
                    "voltage": round(v.voltage, 2),
                    "current": round(v.current, 2),
                    "panel_power": round(v.panel_power, 1),
                })
            return {
                "ok": True,
                "process": self.process_name,
                "id": trend.id if trend else 0,
                "nb_values": trend.nb_values if trend else 0,
                "interval": round(trend.interval, 1) if trend else 0,
                "values": values,
            }
        except GrpcAccessException:
            return {"ok": False, "error": "MPPT trend call failed"}
    
    def execute(self, parameters: list, **kwargs) -> dict:
        """Execute MPPT service commands.
        
        Commands:
        - No command or "status": get MPPT status
        - trend: get MPPT trend data
        """
        if not parameters:
            return self.get_data()
        
        command = parameters[0]
        
        if command == "trend":
            return self.get_trend()
        elif command == "status":
            return self.get_data()
        
        return {"ok": False, "error": f"Unknown MPPT command: {command}"}


class EnergyServiceCollector(BaseServiceCollector):
    """Service collector for EnergyService.
    
    Collects energy controller data including production, consumption,
    and battery balance information.
    """
    
    def _initialize_client(self):
        self._client = EnergyServiceClient()
        self._grpc_server.add_service(self._client)
    
    def get_data(self) -> dict:
        """Get energy system status data."""
        self._ensure_client()
        try:
            info = self._client.GetInformation()
            values = self._client.GetValues()
            trend = self._client.GetTrend()
            
            # Build sources data
            sources_by_instance = {sd.instance: sd for sd in values.sources_data}
            sources = []
            for source in info.sources:
                source_obj = {
                    "instance": int(source.instance_id),
                    "label": source.label,
                    "type": int(source.type),
                    "source_data": {
                        "current": 0.0,
                        "power": 0.0,
                        "communication_ok": True,
                        "device_on": True
                    }
                }
                if source.instance_id in sources_by_instance:
                    source_data = sources_by_instance[source.instance_id]
                    source_obj["source_data"]["current"] = float(source_data.current)
                    source_obj["source_data"]["power"] = float(source_data.power)
                    source_obj["source_data"]["communication_ok"] = bool(source_data.communication_ok)
                    source_obj["source_data"]["device_on"] = bool(source_data.device_on)
                sources.append(source_obj)
            
            # Build batteries data
            batteries = []
            for battery_unit_data in values.batteries_data:
                battery_obj = {
                    "instance": int(battery_unit_data.instance),
                    "battery_data": {
                        "voltage": float(values.main_voltage),
                        "current": float(battery_unit_data.current),
                        "power": float(battery_unit_data.power),
                        "state_of_charge": float(battery_unit_data.state_of_charge) * 10.0,  # BatteryService applies incorrect scaling
                        "energy": float(battery_unit_data.energy) * 10.0  # BatteryService applies incorrect scaling
                    }
                }
                batteries.append(battery_obj)
            
            result = {
                "ok": True,
                "process": self.process_name,
                "main_voltage": float(values.main_voltage),
                "auxiliary_voltage": float(values.auxiliary_voltage),
                "production_power": float(values.production_power),
                "consumption_power": float(values.consumption_power),
                "energy_stock": float(values.energy_stock),
                "battery_balance": float(values.battery_balance),
                "maximum_main_voltage": float(info.maximum_main_voltage),
                "minimum_main_voltage": float(info.minimum_main_voltage),
                "nominal_main_voltage": float(info.nominal_main_voltage),
                "sources": sources,
                "batteries": batteries,
            }
            
            # Add trend data
            if trend.samples:
                result["trend"] = {
                    "samples": [
                        {
                            "main_voltage": float(sample.main_voltage),
                            "auxiliary_voltage": float(sample.auxiliary_voltage),
                            "production_power": float(sample.production_power),
                            "consumption_power": float(sample.consumption_power),
                            "energy_stock": float(sample.energy_stock),
                            "battery_balance": float(sample.battery_balance)
                        }
                        for sample in trend.samples
                    ]
                }
            # _logger.info(f"Energy data collected successfully {result}")
            return result
        except GrpcAccessException:
            return {"ok": False, "error": "Energy service call failed"}
    
    def execute(self, parameters: list, **kwargs) -> dict:
        """Execute Energy service commands.
        
        Commands:
        - No parameters or "status": get energy status
        """
        # Energy service doesn't take parameters for status
        return self.get_data()


class BatteryServiceCollector(BaseServiceCollector):
    """Service collector for BatteryService.
    
    Collects battery data including voltage, current, power, state of charge,
    and energy variations.
    """
    
    def _initialize_client(self):
        self._client = BatteryServiceClient()
        self._grpc_server.add_service(self._client)
    
    def get_data(self) -> dict:
        """Get battery status data."""
        self._ensure_client()
        try:
            info = self._client.GetInformation('parameters')
            values = self._client.GetValues()
            trend = self._client.GetTrend()
            
            battery_label = "Battery_0"
            try:
                if info.battery.device_label:
                    battery_label = info.battery.device_label
                elif info.controller.device_label:
                    battery_label = info.controller.device_label
            except (AttributeError, ValueError):
                pass
            
            # Extract battery info
            state_of_charge = 0.0
            nominal_capacity = 100.0  # Default value (Ah)
            nominal_voltage = 12.0    # Default value (V)
            device_model = "Unknown"
            
            if hasattr(info, 'battery') and info.battery:
                # Get state_of_charge if available
                if hasattr(info.battery, 'state_of_charge'):
                    # BatteryService may apply incorrect scaling; compensate by multiplying by 10
                    state_of_charge = float(info.battery.state_of_charge) * 10.0
                    _logger.debug(f"Battery SOC from info: {state_of_charge}%")
                
                # Get device model if available
                if hasattr(info.battery, 'device_model') and info.battery.device_model:
                    device_model = info.battery.device_model
                    _logger.debug(f"Battery device_model: {device_model}")
                
                # Get nominal parameters if available and non-zero, otherwise use defaults
                if hasattr(info.battery, 'nominal_capacity') and info.battery.nominal_capacity:
                    nominal_capacity = float(info.battery.nominal_capacity)
                    _logger.debug(f"Battery nominal_capacity: {nominal_capacity}Ah")
                if hasattr(info.battery, 'nominal_voltage') and info.battery.nominal_voltage:
                    nominal_voltage = float(info.battery.nominal_voltage)
                    _logger.debug(f"Battery nominal_voltage: {nominal_voltage}V")
            
            _logger.debug(f"Battery state_of_charge={state_of_charge}%, nominal_capacity={nominal_capacity}Ah, nominal_voltage={nominal_voltage}V")
            
            battery_obj = {
                "ok": True,
                "process": self.process_name,
                "instance": 0,
                "label": battery_label,
                "device_model": device_model,
                "nominal_capacity": nominal_capacity,
                "nominal_voltage": nominal_voltage,
                "voltage": float(values.voltage) if values.voltage else 0.0,
                "current": float(values.current) if values.current else 0.0,
                "power": float(values.voltage * values.current) if values.voltage and values.current else 0.0,
                "state_of_charge": state_of_charge,
                "energy": ((state_of_charge / 100.0) * nominal_capacity * nominal_voltage) if state_of_charge else 0.0,
                "trend": {
                    "samples": [
                        {
                            "timestamp": sample.timestamp,
                            "voltage": float(sample.voltage),
                            "power": float(sample.power),
                            "state_of_charge": float(sample.state_of_charge) * 10.0,
                            "energy_variation": float(sample.energy_variation)
                        }
                        for sample in trend.samples
                    ] if trend.samples else []
                }
            }
            return battery_obj
        except GrpcAccessException:
            return {"ok": False, "error": "Battery service call failed"}
    
    def execute(self, parameters: list, **kwargs) -> dict:
        """Execute Battery service commands.
        
        Commands:
        - No parameters or "status": get battery status
        - trend: get battery trend data
        """
        if not parameters:
            return self.get_data()
        
        command = parameters[0]
        
        if command == "status":
            return self.get_data()
        elif command == "trend":
            # Get trend data only
            self._ensure_client()
            try:
                trend = self._client.GetTrend()
                trend_data = {
                    "ok": True,
                    "process": self.process_name,
                    "samples": [
                        {
                            "timestamp": sample.timestamp,
                            "voltage": float(sample.voltage),
                            "power": float(sample.power),
                            "state_of_charge": float(sample.state_of_charge) * 10.0,
                            "energy_variation": float(sample.energy_variation)
                        }
                        for sample in trend.samples
                    ] if trend.samples else []
                }
                return trend_data
            except GrpcAccessException:
                return {"ok": False, "error": "Battery trend call failed"}
        
        return {"ok": False, "error": f"Unknown battery command: {command}"}


class GNSSServiceCollector(BaseServiceCollector):
    """Service collector for GNSS service.
    
    Collects GNSS (Global Navigation Satellite System) status data.
    """
    
    def _initialize_client(self):
        self._client = GNSSClient()
        self._grpc_server.add_service(self._client)
    
    def get_data(self) -> dict:
        """Get GNSS status data."""
        self._ensure_client()
        try:
            status = self._client.gnss_status()
            return {
                "ok": True,
                "process": self.process_name,
                "fixed": status.fixed,
                "fix_time": status.fix_time,
                "gnss_time": status.gnss_time,
                "nb_satellites_in_fix": status.nb_satellites_in_fix,
            }
        except GrpcAccessException:
            return {"ok": False, "error": "GNSS service call failed"}
    
    def execute(self, parameters: list, **kwargs) -> dict:
        """Execute GNSS service commands.
        
        Commands:
        - No parameters or "status": get GNSS status
        """
        return self.get_data()


class NetworkServiceCollector:
    """Service collector for Network service.
    
    Collects network status, configurations, and handles network interface commands.
    This is a singleton collector that works at the system level rather than per-process.
    """
    
    def __init__(self, system_collector: 'NavigationSystemCollector'):
        # Network service is system-level, not process-level
        self._system_collector = system_collector
        self._client = None
        self._lock = threading.Lock()
    
    def _ensure_client(self):
        """Ensure the NetworkClient is initialized."""
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = NetworkClient()
                    self._system_collector._server.add_service(self._client)
    
    def get_status(self) -> dict:
        """Get network status."""
        self._ensure_client()
        try:
            status = self._client.network_status("update")
        except GrpcAccessException:
            return {"ok": False, "error": "Network service unavailable"}
        
        interfaces = []
        for iface in status.interfaces():
            conn = iface.connection
            interfaces.append({
                "name": iface.name,
                "device_name": iface.device_name,
                "state": iface.state,
                "type": iface.device_type(),
                "function": iface.function,
                "connection_name": conn.name,
            })
        return {
            "ok": True,
            "status": status.status,
            "details": status.details,
            "nm_running": status.nm_running,
            "interfaces": interfaces,
        }
    
    def get_configurations(self) -> dict:
        """Return the available global network configurations."""
        self._ensure_client()
        try:
            reply = self._client.get_global_configuration()
        except GrpcAccessException:
            return {"ok": False, "error": "Network service unavailable"}
        return {"ok": True, "configurations": reply.configuration_names()}
    
    def get_connection_definitions(self) -> dict:
        """Return the available connection names (configuration names)."""
        self._ensure_client()
        try:
            reply = self._client.get_global_configuration()
        except GrpcAccessException:
            return {"ok": False, "error": "Network service unavailable"}
        return {"ok": True, "connections": reply.configuration_names()}
    
    def set_global_configuration(self, config_name: str) -> dict:
        """Apply a global network configuration."""
        self._ensure_client()
        try:
            self._client.set_global_configuration(config_name)
        except GrpcAccessException:
            return {"ok": False, "error": "Network service unavailable"}
        return {"ok": True, "configuration": config_name}
    
    def interface_cmd(self, interface_name: str, connection_name: str, cmd: str) -> dict:
        """Send a command to a network interface (up, down, delete, add connection)."""
        self._ensure_client()
        try:
            if cmd == "add":
                # Add a connection to an interface
                iface_pb = NetInterfacePb()
                iface_pb.name = interface_name
                result = self._client.set_configuration("add", connection_name, iface_pb)
            else:
                # For up, down, delete commands
                iface_pb = NetInterfacePb()
                iface_pb.name = interface_name
                result = self._client.interface_command(cmd, iface_pb)
        except GrpcAccessException:
            return {"ok": False, "error": "Network service unavailable"}
        return {
            "ok": True,
            "status": result.status,
            "details": result.details,
        }
    
    def execute(self, parameters: list, **kwargs) -> dict:
        """Execute Network service commands.
        
        Commands:
        - No parameters or "status": get network status
        - configurations: get network configurations
        - connections: get connection definitions
        - set_configuration: set global configuration (needs config_name in kwargs)
        - interface: send interface command (needs interface_name, connection_name, cmd in kwargs)
        """
        if not parameters:
            return self.get_status()
        
        command = parameters[0]
        
        if command == "status":
            return self.get_status()
        elif command == "configurations":
            return self.get_configurations()
        elif command == "connections":
            return self.get_connection_definitions()
        elif command == "set_configuration":
            config_name = kwargs.get("config_name")
            if not config_name:
                return {"ok": False, "error": "missing 'config_name' parameter"}
            return self.set_global_configuration(config_name)
        elif command == "interface":
            interface_name = kwargs.get("interface_name")
            connection_name = kwargs.get("connection_name")
            cmd = kwargs.get("cmd")
            if not interface_name or not cmd:
                return {"ok": False, "error": "missing 'interface_name' or 'cmd' parameter"}
            return self.interface_cmd(interface_name, connection_name or "", cmd)
        
        return {"ok": False, "error": f"Unknown network command: {command}"}


# Service endpoint mapping: endpoint_handle -> (CollectorClass, protobuf_service_name, is_system_level)
# This is the hard-coded dictionary as required by the refactoring
# Note: Service collectors for per-process services are defined above
ENDPOINT_SERVICE_MAP: Dict[str, Tuple[Optional[Type[BaseServiceCollector]], str, bool]] = {
    "system": (None, None, True),  # Handled by NavigationSystemCollector
    "status": (None, None, True),  # Alias for system
    "process": (None, None, True),  # Handled by NavigationSystemCollector
    "settings": (None, None, True),  # Handled by NavigationSystemCollector
    "log": (None, None, True),  # Handled by NavigationSystemCollector
    "network": (NetworkServiceCollector, "Network", True),  # System-level singleton
    "console": (ConsoleServiceCollector, "NavigationConsole", False),
    "nmea2000": (NMEA2000ServiceCollector, "Nmea2000ControllerService", False),
    "engine": (EngineServiceCollector, "EngineData", False),
    "mppt": (MPPTServiceCollector, "MPPTService", False),
    "energy": (EnergyServiceCollector, "EnergyService", False),
    "battery": (BatteryServiceCollector, "BatteryService", False),
    "gnss": (GNSSServiceCollector, "GNSSService", False),
}

# Reverse mapping: protobuf service name -> endpoint handle
SERVICE_TO_ENDPOINT: Dict[str, str] = {
    v[1]: k for k, v in ENDPOINT_SERVICE_MAP.items() if v[1] is not None
}


class NavigationSystemCollector:
    """Top-level collector that handles all requests from the web server and routes them.
    
    This collector holds the connection to a single gRPC agent server and lazily
    instantiates the service clients (Agent, Console, Network). All returned data
    is serialisable JSON (no protobuf objects leak to the HTTP layer).
    
    The collector handles the global system status and routes requests to the
    appropriate ProcessCollector and ServiceCollector instances.
    
    Uses ProcessCollector to manage per-process connections and BaseServiceCollector
    subclasses for each service type.
    """

    # Refresh interval for agent status cache (seconds)
    REFRESH_INTERVAL = 10.0

    def __init__(self, address: str, port: int, secure: bool = False, language: str = "en"):
        self._address = address
        self._port = port
        self._secure = secure
        self._language = language
        # The security mode (and CA certificate, shared at class level) applies
        # to the agent and to all console connections, since all gRPC servers in
        # a deployment share the same certificate.
        self._server = GrpcClient.get_client(f"{address}:{port}", secure=secure)
        self._agent = AgentClient()
        self._server.add_service(self._agent)
        
        # Log stream tracking for multiple concurrent streams
        self._log_streams = {}  # process_name -> AgentClient instance
        self._log_streams_lock = threading.Lock()
        
        # System-level service collectors (singleton, not per-process)
        self._network_collector: Optional[NetworkServiceCollector] = None
        
        # Agent status cache
        self._last_status: Optional[Any] = None
        self._last_status_time: float = 0.0
        self._status_lock = threading.Lock()
        
        # Per-process collectors
        self._process_collectors: Dict[str, ProcessCollector] = {}  # process_name -> ProcessCollector
        
        # Service collector cache: endpoint_key -> ServiceCollector instance
        # Format: "api/{service_handle}/{process_name}" -> ServiceCollector
        self._service_collector_cache: Dict[str, BaseServiceCollector] = {}
        
        # Main lock for thread safety
        self._lock = threading.Lock()
        
        # Note: Collector initialization is lazy. Call refresh_status() to force initialization,
        # or it will be initialized automatically on the first request.

    @property
    def agent_address(self) -> str:
        """The full agent address (host:port)."""
        return f"{self._address}:{self._port}"

    @property
    def agent_host(self) -> str:
        """Host address of the agent gRPC server (without port)."""
        return self._address

    @property
    def secure(self) -> bool:
        """Whether the agent connection uses secure gRPC."""
        return self._secure

    @property
    def language(self) -> str:
        """Configured UI language."""
        return self._language

    @property
    def server_state(self) -> int:
        """The state of the agent gRPC server connection."""
        return self._server.state

    def _get_network_collector(self) -> 'NetworkServiceCollector':
        """Get or create the NetworkServiceCollector."""
        if self._network_collector is None:
            self._network_collector = NetworkServiceCollector(self)
        return self._network_collector

    def _get_process_collector(self, process_name: str) -> Optional[ProcessCollector]:
        """Get or create a ProcessCollector for a process.
        
        Uses the cached agent status to get process details (port, secure).
        Returns None if process is not running or not found.
        """
        # Ensure we have current status
        self._get_agent_status()
        
        if process_name not in self._process_collectors:
            # Get process info from cached status
            proc_info = self._get_process_info_from_cache(process_name)
            if proc_info is None:
                return None
            grpc_port, secure = proc_info
            self._process_collectors[process_name] = ProcessCollector(
                self, process_name, grpc_port, secure
            )
        return self._process_collectors[process_name]
    
    def _get_process_info_from_cache(self, process_name: str) -> Optional[Tuple[int, bool]]:
        """Get process port and secure flag from cached agent status."""
        system = self._last_status
        if system is None:
            return None
        for proc in system.get_processes():
            if proc.name == process_name:
                return proc.grpc_port, bool(proc.secure_grpc)
        return None
    
    def _get_agent_status(self, force_refresh: bool = False) -> Optional[Any]:
        """Get the agent system status, using cache when possible.
        
        The status is cached and automatically refreshed based on REFRESH_INTERVAL.
        Can be forced to refresh with force_refresh=True.
        
        Args:
            force_refresh: If True, bypass cache and query agent directly
            
        Returns:
            NavigationSystemMsgProxy or None if failed
        """
        current_time = time.time()
        
        # Check if we need to refresh
        if force_refresh or self._last_status is None or (current_time - self._last_status_time) > self.REFRESH_INTERVAL:
            with self._status_lock:
                # Double-check after acquiring lock
                if force_refresh or self._last_status is None or (current_time - self._last_status_time) > self.REFRESH_INTERVAL:
                    _logger.debug(f"_get_agent_status: Need to refresh status (force={force_refresh}, last_status={self._last_status is not None})")
                    self._connect()
                    if self._server.not_connected:
                        _logger.debug("_get_agent_status: Server not connected, returning None")
                        return None
                    try:
                        system = self._agent.system_cmd("status")
                        if system is not None:
                            self._last_status = system
                            self._last_status_time = current_time
                            # Rebuild process and service collectors from the new status
                            _logger.debug("_get_agent_status: Calling _rebuild_collectors_from_status()")
                            self._rebuild_collectors_from_status()
                        else:
                            _logger.debug("_get_agent_status: system_cmd returned None")
                    except Exception as e:
                        _logger.error(f"Failed to get agent status: {e}")
                        return self._last_status  # Return stale data if available
        
        return self._last_status
    
    def _rebuild_collectors_from_status(self):
        """Rebuild process and service collectors from the cached agent status.
        
        This is called when a new agent status is retrieved. It:
        1. Identifies all currently running processes and their services
        2. Creates ProcessCollector instances for new processes
        3. Creates ServiceCollector instances for all services on each process
        4. Removes collectors for processes that are no longer running
        """
        system = self._last_status
        if system is None:
            _logger.debug("Cannot rebuild collectors: _last_status is None")
            return
        
        current_processes = {proc.name: proc for proc in system.get_processes() if proc.state == "RUNNING"}
        _logger.debug(f"Starting rebuild of collectors from status with {len(current_processes)} running processes")
        
        # Log which processes and services were found
        for proc_name, proc in current_processes.items():
            service_names = [svc.rpc_service for svc in proc.services]
            _logger.debug(f"  Process {proc_name} has services: {service_names}")
            for svc_name in service_names:
                endpoint_handle = SERVICE_TO_ENDPOINT.get(svc_name)
                if endpoint_handle:
                    _logger.debug(f"    Service {svc_name} maps to endpoint {endpoint_handle}")
                else:
                    _logger.debug(f"    Service {svc_name} has NO endpoint mapping")
        
        with self._lock:
            # Find processes that have stopped
            stopped_processes = [name for name in self._process_collectors if name not in current_processes]
            _logger.debug(f"   Stopped processes: {stopped_processes}")
            # Remove collectors for stopped processes
            for process_name in stopped_processes:
                _logger.debug(f"Removing collector for stopped process {process_name}")
                self._remove_process_collector(process_name)
            
            # Create/update ProcessCollector and ServiceCollectors for each running process
            for process_name, proc in current_processes.items():
                # Create ProcessCollector if it doesn't exist
                if process_name not in self._process_collectors:
                    process_collector = ProcessCollector(
                        self,
                        process_name,
                        proc.grpc_port,
                        bool(proc.secure_grpc)
                    )
                    self._process_collectors[process_name] = process_collector
                    _logger.debug(f"Created ProcessCollector for process {process_name} with port {proc.grpc_port}")
                else:
                    # Update existing ProcessCollector if port changed
                    existing_collector = self._process_collectors[process_name]
                    if existing_collector.port != proc.grpc_port:
                        _logger.debug(f"Updating port for process {process_name} from {existing_collector.port} to {proc.grpc_port}")
                        # Close existing and create new with updated port
                        existing_collector.close()
                        del self._process_collectors[process_name]
                        process_collector = ProcessCollector(
                            self,
                            process_name,
                            proc.grpc_port,
                            bool(proc.secure_grpc)
                        )
                        self._process_collectors[process_name] = process_collector
                        _logger.debug(f"Created ProcessCollector for process {process_name} with port {proc.grpc_port}")
                    else:
                        process_collector = existing_collector
                
                # Get or create the ProcessCollector
                process_collector = self._process_collectors[process_name]
                
                # For each service in this process, create the ServiceCollector
                for svc in proc.services:
                    # Map protobuf service name to endpoint handle
                    endpoint_handle = SERVICE_TO_ENDPOINT.get(svc.rpc_service)
                    if endpoint_handle is None:
                        continue
                    
                    # Get the collector class from ENDPOINT_SERVICE_MAP
                    endpoint_info = ENDPOINT_SERVICE_MAP.get(endpoint_handle)
                    if endpoint_info is None or endpoint_info[0] is None:
                        continue
                    
                    collector_class = endpoint_info[0]
                    endpoint_key = f"api/{endpoint_handle}/{process_name}"
                    
                    # Skip if already created
                    if endpoint_key in self._service_collector_cache:
                        continue
                    
                    # Create the service collector
                    try:
                        # Get gRPC server for this process
                        _logger.debug(f"  Getting gRPC server for process {process_name}")
                        grpc_server = process_collector.get_grpc_server()
                        if grpc_server is None:
                            _logger.debug(f"  gRPC server is None for process {process_name}, skipping")
                            continue

                        _logger.debug(f"  Creating {collector_class.__name__} for {process_name}/{endpoint_handle}")
                        service_collector = collector_class(process_collector, grpc_server)
                        self._service_collector_cache[endpoint_key] = service_collector
                        _logger.debug(f"  Successfully created {collector_class.__name__} and cached with key {endpoint_key}")
                    except Exception as e:
                        _logger.warning(f"Failed to create {collector_class.__name__} for {process_name}/{endpoint_handle}: {e}")
                        continue
        
        _logger.debug(f"Rebuild complete: {len(self._service_collector_cache)} service collectors in cache")
    
    def _remove_process_collector(self, process_name: str):
        """Remove a ProcessCollector and all its ServiceCollectors.
        
        Also removes any cached ServiceCollector instances that reference this process.
        """
        if process_name in self._process_collectors:
            process_collector = self._process_collectors[process_name]
            # Close the process collector (cleans up gRPC connections and service collectors)
            process_collector.close()
            del self._process_collectors[process_name]
            
            # Remove any cached service collectors for this process
            keys_to_remove = [
                key for key in self._service_collector_cache 
                if key.endswith(f"/{process_name}")
            ]
            for key in keys_to_remove:
                del self._service_collector_cache[key]
    
    def refresh_status(self):
        """Force a refresh of the agent status and rebuild collectors.
        
        This should be called:
        - Upon start
        - Upon refresh timer lapse
        - Upon process start or stop notification
        """
        self._get_agent_status(force_refresh=True)

    def get_settings(self, target: str) -> dict:
        """Get settings for a process or special target (agent, network).
        
        Args:
            target: Process name or special target ('agent', 'network')
            
        Returns:
            Dictionary with 'ok', 'settings_file', 'settings_content', and optionally 'error'
        """
        self._connect()
        if self._server.not_connected:
            return {"ok": False, "error": "Agent gRPC server unreachable"}
        
        settings = self._agent.get_settings(target)
        if settings is None:
            return {"ok": False, "error": f"Failed to retrieve settings for {target}"}
        
        if settings.err_code != 0:
            return {"ok": False, "error": settings.response, "settings_file": settings.settings_file}
        
        return {
            "ok": True,
            "settings_file": settings.settings_file,
            "settings_content": settings.settings_content,
        }

    def set_settings(self, target: str, settings_content: str) -> dict:
        """Set settings for a process or special target (agent, network).
        
        Args:
            target: Process name or special target ('agent', 'network')
            settings_content: The YAML settings content to write
            
        Returns:
            Dictionary with 'ok' and optionally 'error'
        """
        self._connect()
        if self._server.not_connected:
            return {"ok": False, "error": "Agent gRPC server unreachable"}
        
        response = self._agent.set_settings(target, settings_content)
        if response is None:
            return {"ok": False, "error": f"Failed to set settings for {target}"}
        
        if response.err_code != 0:
            return {"ok": False, "error": response.response}
        
        return {"ok": True, "response": response.response}

    def _get_service_collector(self, process_name: str, service_type: str, collector_class):
        """Get a ServiceCollector for a process and service type.
        
        This is a legacy method that does direct cache lookup.
        It's kept for backward compatibility.
        """
        endpoint_key = f"api/{service_type}/{process_name}"
        return self._service_collector_cache.get(endpoint_key)

    def _connect(self):
        """Ensure the agent connection is established."""
        if self._server.not_connected:
            self._server.connect()
            self._server.wait_connect(5.0)

    def service_execution(self, service_handle: str, parameters: list, **kwargs) -> dict:
        """Execute a service command based on service_handle and parameters.
        
        This is the main entry point for all API requests from the web server.
        It routes requests to the appropriate service collector or handler method.
        
        The routing works as follows:
        1. For system-level services (system, status, process, settings, log, network):
           - Route directly to handler methods
        2. For per-process services (console, nmea2000, engine, mppt, energy, battery):
           - If no process name in parameters, return list of processes with this service
           - Otherwise, do direct lookup in _service_collector_cache
        
        Args:
            service_handle: The service handle from the URL path (e.g., 'system', 'process', 'console')
            parameters: List of parameters from the URL path
            **kwargs: Additional keyword arguments from the request body or query params
            
        Returns:
            Dictionary with the result of the operation, must include 'ok' key
        """
        # Handle system-level services first
        if service_handle == "log":
            return self._handle_log_service(parameters, **kwargs)
        elif service_handle in ("system", "status"):
            # "status" is an alias for "system"
            return self._handle_system_service(parameters, **kwargs)
        elif service_handle == "process":
            return self._handle_process_service(parameters, **kwargs)
        elif service_handle == "settings":
            return self._handle_settings_service(parameters, **kwargs)
        elif service_handle == "network":
            # Network is system-level, handle directly
            return self._handle_network_service(parameters, **kwargs)
        elif service_handle == "energy_available":
            # Check if EnergyService is available
            return {"ok": True, "available": self.is_energy_service_available()}
        
        # Get the endpoint info
        endpoint_info = ENDPOINT_SERVICE_MAP.get(service_handle)
        if endpoint_info is None:
            return {"ok": False, "error": f"Unknown service handle: {service_handle}"}
        
        is_system_level = endpoint_info[2]
        
        # For system-level services (shouldn't reach here as we handle all above)
        if is_system_level:
            return {"ok": False, "error": f"Unexpected system-level service: {service_handle}"}
        
        # For per-process services
        if not parameters:
            # No process name provided - return list of processes with this service
            return self._get_service_processes(service_handle)
        
        # Build endpoint key and do direct lookup
        process_name = parameters[0]
        endpoint_key = f"api/{service_handle}/{process_name}"
        
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"Service {service_handle} not available for process {process_name}"}
        
        # Execute with remaining parameters
        remaining_params = parameters[1:] if len(parameters) > 1 else []
        return service_collector.execute(remaining_params, **kwargs)
    
    def _get_service_processes(self, service_handle: str) -> dict:
        """Get list of processes that have a specific service.
        
        Uses the cached agent status to determine which processes have which services.
        If there's exactly one process, returns its data directly.
        """
        system = self._get_agent_status()
        if system is None:
            return {"ok": False, "error": "Agent status not available"}
        
        # Get the protobuf service name for this handle
        endpoint_info = ENDPOINT_SERVICE_MAP.get(service_handle)
        if endpoint_info is None or endpoint_info[1] is None:
            return {"ok": True, "processes": [], "service": service_handle}
        
        service_name = endpoint_info[1]
        
        # Find all running processes with this service
        processes = []
        for proc in system.get_processes():
            if proc.state == "RUNNING":
                for svc in proc.services:
                    if svc.rpc_service == service_name:
                        processes.append(proc.name)
                        break
        
        # If there's exactly one process, return its data directly
        if len(processes) == 1:
            process_name = processes[0]
            endpoint_key = f"api/{service_handle}/{process_name}"
            service_collector = self._service_collector_cache.get(endpoint_key)
            if service_collector:
                return service_collector.execute([])
        
        # Return list of processes with this service
        return {"ok": True, "processes": processes, "service": service_handle}

    def _handle_log_service(self, parameters: list, **kwargs) -> dict:
        """Handle log service commands.
        
        Commands:
        - stream/{process}: start log stream (handled by web server directly)
        - stop: stop all log streams
        - stop/{process}: stop log stream for specific process
        """
        if not parameters:
            return {"ok": False, "error": "Log service requires a command"}
        
        command = parameters[0]
        
        if command == "stop":
            if len(parameters) >= 2:
                # Stop specific process stream
                process_name = parameters[1]
                self.stop_log_stream(process_name)
                return {"ok": True, "message": f"Stopped log stream for {process_name}"}
            else:
                # Stop all log streams
                self.stop_log_stream()
                return {"ok": True, "message": "Stopped all log streams"}
        elif command == "stream" and len(parameters) >= 2:
            # This should be handled by the web server directly via SSE
            process_name = parameters[1]
            return {"ok": False, "error": "Log stream should be requested via SSE endpoint"}
        
        return {"ok": False, "error": f"Unknown log command: {command}"}

    def _handle_system_service(self, parameters: list, **kwargs) -> dict:
        """Handle system-level service commands.
        
        Commands:
        - status: get system status
        - halt, reboot, navigation_restart: system commands
        """
        if not parameters:
            # Check if cmd was passed in the request body (POST with {cmd: "..."})
            if 'cmd' in kwargs and kwargs['cmd']:
                command = kwargs['cmd']
            else:
                # Default to status
                return self.system_status()
        else:
            command = parameters[0]
        
        _logger.debug(f"Handling system service command: {command}")
        if command == "status":
            return self.system_status()
        else:
            # System command
            _logger.info(f"Executing system command: {command}")
            return self.system_cmd(command)

    def _handle_process_service(self, parameters: list, **kwargs) -> dict:
        """Handle process-level service commands.
        
        API paths:
        - /api/process/{target}/{cmd} where cmd is start/stop/restart
        - /api/process/{process_name}/status -> get console status
        """
        if not parameters:
            return {"ok": False, "error": "Process service requires a command or process name"}
        
        # /api/process/{target}/{cmd}
        # First parameter is the target/process name, second is the command
        if len(parameters) >= 2:
            target = parameters[0]
            cmd = parameters[1]
            
            # Check if cmd is a process control command
            if cmd in ("start", "stop", "restart"):
                return self.process_cmd(cmd, target)
            
            # Handle console status
            if cmd == "status":
                return self.console_status(target)
            
            # Handle coupler commands
            elif cmd == "coupler" and len(parameters) >= 3:
                # /api/process/{process_name}/coupler/{coupler_name}
                coupler_name = parameters[2]
                coupler_cmd = kwargs.get("cmd")
                if not coupler_cmd:
                    return {"ok": False, "error": "missing 'cmd' parameter for coupler command"}
                return self.coupler_cmd(target, coupler_name, coupler_cmd)
        
        # Single parameter: /api/process/{process_name}
        # This could be a request for process status
        process_name = parameters[0]
        return self.console_status(process_name)

    def _handle_settings_service(self, parameters: list, **kwargs) -> dict:
        """Handle settings service commands.
        
        API paths:
        - GET /api/settings/{target} - retrieve settings
        - POST /api/settings/{target} - save settings with {settings_content: "..."}
        
        where target is a process name, 'agent', or 'network'
        """
        if not parameters:
            return {"ok": False, "error": "Settings service requires a target"}
        
        target = parameters[0]
        
        # If settings_content is provided in kwargs, this is a POST request to save settings
        if 'settings_content' in kwargs:
            return self.set_settings(target, kwargs['settings_content'])
        
        # Otherwise, this is a GET request to retrieve settings
        return self.get_settings(target)
    
    def _handle_network_service(self, parameters: list, **kwargs) -> dict:
        """Handle network service commands."""
        net_collector = self._get_network_collector()
        if net_collector is None:
            return {"ok": False, "error": "Network service unavailable"}
        return net_collector.execute(parameters, **kwargs)

    def console_status(self, process_name: str) -> dict:
        """Return the console view (servers + couplers) of a process."""
        endpoint_key = f"api/console/{process_name}"
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"Console service not available for {process_name}"}
        return service_collector.get_data()

    def coupler_cmd(self, process_name: str, coupler_name: str, cmd: str) -> dict:
        """Send a command to a coupler on a process console."""
        endpoint_key = f"api/console/{process_name}"
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"Console service not available for {process_name}"}
        if hasattr(service_collector, 'coupler_cmd'):
            return service_collector.coupler_cmd(coupler_name, cmd)
        return {"ok": False, "error": "Coupler command not supported"}

    def system_status(self) -> dict:
        """Return the full navigation system status as a JSON-serialisable dict."""
        system = self._get_agent_status()
        
        if system is None:
            # Check if server is connected
            self._connect()
            if self._server.not_connected:
                return {
                    "connected": False,
                    "agent_address": self.agent_address,
                    "error": "Agent gRPC server unreachable",
                }
            return {
                "connected": False,
                "agent_address": self.agent_address,
                "error": "Agent returned no status",
            }
        
        return {
            "connected": True,
            "agent_address": self.agent_address,
            "system": self._system_to_dict(system),
        }

    def _system_to_dict(self, system) -> dict:
        """Convert a NavigationSystemMsgProxy into a plain dict.
        
        Uses ProcessCollector.process_to_dict for process-level data and
        ConsoleServiceCollector.servers_to_dict for server/console data.
        """
        processes = []
        for proc in system.get_processes():
            # Get process-level data
            process_dict = ProcessCollector.process_to_dict(proc, self)
            
            # Get server/console data
            servers = ConsoleServiceCollector.servers_to_dict(self, proc.name, proc.servers)
            
            # Combine them
            process_dict["servers"] = servers
            processes.append(process_dict)
        
        return {
            "id": system.id,
            "name": system.name,
            "version": system.version,
            "start_time": system.start_time,
            "hostname": system.hostname,
            "ip_address": system.ip_address,
            "settings": system.settings,
            "processes": processes,
        }

    def process_cmd(self, cmd: str, target: str) -> dict:
        """Send a command (start/stop/...) to a registered process via the agent."""
        # Delegate to ProcessCollector static method
        result = ProcessCollector.send_cmd_to_process(self, target, cmd)
        # Force refresh of agent status after start/stop/restart to update collectors immediately
        _logger.debug(f"Process {target}command: {cmd} executed")
        if cmd in ("start", "stop", "restart"):
            _logger.debug(f"Forcing status refresh after process command: {cmd} {target}")
            self._get_agent_status(force_refresh=True)
        return result

    def system_cmd(self, cmd: str) -> dict:
        """Send a system command (halt/reboot/navigation_restart) to the agent."""
        _logger.info(f"Web server sending system command to agent: {cmd}")
        if cmd not in ("halt", "reboot", "navigation_restart"):
            return {"ok": False, "error": f"Unsupported system command: {cmd}"}
        with self._lock:
            self._connect()
            if self._server.not_connected:
                _logger.error("Agent gRPC server unreachable for system command")
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            err = self._agent.system_cmd(cmd)
            if err is None:
                _logger.error(f"System command '{cmd}' failed on agent")
                return {"ok": False, "error": f"System command '{cmd}' failed"}
            _logger.info(f"System command '{cmd}' succeeded with err_code: {err}")
            # Force refresh of agent status after system commands
            self._get_agent_status(force_refresh=True)
            return {"ok": True, "err_code": err}

    def start_log_stream(self, process_name: str, line_callback) -> bool:
        """Start streaming logs for a process via the agent GetSystemLog.

        Uses the callback-based streaming reader (non-blocking). The
        line_callback is invoked for each received log line. Supports multiple
        concurrent log streams for different processes.
        """
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return False
        
        # Create a dedicated agent client for this process's log stream
        with self._log_streams_lock:
            if process_name not in self._log_streams:
                # Create a new agent client for this process
                process_agent = AgentClient()
                self._server.add_service(process_agent)
                self._log_streams[process_name] = process_agent
            else:
                # Stream already exists for this process
                process_agent = self._log_streams[process_name]
        
        try:
            process_agent.get_log(process_name, line_callback)
        except GrpcAccessException:
            _logger.error(f"Error starting log stream for {process_name}")
            return False
        return True

    def stop_log_stream(self, process_name: str = None):
        """Stop the active log stream(s).
        
        If process_name is provided, stops only that process's stream.
        If no process_name is provided, stops all active log streams.
        """
        with self._log_streams_lock:
            if process_name is not None:
                # Stop only the specified process stream
                if process_name in self._log_streams:
                    self._log_streams[process_name].stop_log()
                    del self._log_streams[process_name]
            else:
                # Stop all active log streams
                for process_agent in self._log_streams.values():
                    process_agent.stop_log()
                self._log_streams.clear()

    def network_status(self) -> dict:
        """Get network status from the NetworkServiceCollector."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net_collector = self._get_network_collector()
            return net_collector.get_status()

    def network_configurations(self) -> dict:
        """Return the available global network configurations."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net_collector = self._get_network_collector()
            return net_collector.get_configurations()

    def network_connection_definitions(self) -> dict:
        """Return the available connection names (configuration names)."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net_collector = self._get_network_collector()
            return net_collector.get_connection_definitions()

    def engine_list(self) -> dict:
        """Return the list of available engines across processes with EngineData.

        Each process with an EngineData service is served by an
        EngineServiceCollector that caches its engine parameters; the collector's
        get_engine_list() produces the summaries (with live runtime data).
        """
        system = self._get_agent_status()
        if system is None:
            return {"ok": False, "error": "Agent status not available"}
        
        engines = []
        for proc in system.get_processes():
            if proc.state == "RUNNING":
                for svc in proc.services:
                    if svc.rpc_service == "EngineData":
                        endpoint_key = f"api/engine/{proc.name}"
                        service_collector = self._service_collector_cache.get(endpoint_key)
                        if service_collector and hasattr(service_collector, 'get_engine_list'):
                            try:
                                engines.extend(service_collector.get_engine_list())
                            except Exception as e:
                                _logger.warning(f"Error retrieving engine list from {proc.name}: {e}")
                        break
        return {"ok": True, "engines": engines}

    def engine_data(self, engine_id: int) -> dict:
        """Return detailed data for a specific engine instance.

        Iterates processes with an EngineData service and returns the first one
        able to serve the requested engine instance via its EngineServiceCollector.
        """
        system = self._get_agent_status()
        if system is None:
            return {"ok": False, "error": "Agent status not available"}
        
        for proc in system.get_processes():
            if proc.state == "RUNNING":
                for svc in proc.services:
                    if svc.rpc_service == "EngineData":
                        endpoint_key = f"api/engine/{proc.name}"
                        service_collector = self._service_collector_cache.get(endpoint_key)
                        if service_collector and hasattr(service_collector, 'get_engine_data'):
                            try:
                                result = service_collector.get_engine_data(engine_id)
                                if result.get("ok"):
                                    return result
                            except Exception as e:
                                _logger.warning(f"Error getting engine data from {proc.name}: {e}")
                        break
        return {"ok": False, "error": f"Engine {engine_id} not found or no process with EngineData service"}

    def energy_status(self):
        """Return energy management system status data.
        
        Returns a valid response with empty data if EnergyService is not running,
        so the EMS page can still display.
        """
        try:
            # Build response with default empty values
            result = {
                "ok": True,
                "controller": {},
                "batteries": [],
                "sources": []
            }
            
            system = self._get_agent_status()
            if system is None:
                return result
            
            # Try to get EnergyService data if available
            for proc in system.get_processes():
                if proc.state == "RUNNING":
                    for svc in proc.services:
                        if svc.rpc_service == "EnergyService":
                            endpoint_key = f"api/energy/{proc.name}"
                            service_collector = self._service_collector_cache.get(endpoint_key)
                            if service_collector:
                                try:
                                    energy_data = service_collector.get_data()
                                    if energy_data.get("ok"):
                                        result["controller"] = {
                                            "main_voltage": energy_data.get("main_voltage", 0.0),
                                            "auxiliary_voltage": energy_data.get("auxiliary_voltage", 0.0),
                                            "production_power": energy_data.get("production_power", 0.0),
                                            "consumption_power": energy_data.get("consumption_power", 0.0),
                                            "energy_stock": energy_data.get("energy_stock", 0.0),
                                            "battery_balance": energy_data.get("battery_balance", 0.0),
                                            "maximum_main_voltage": energy_data.get("maximum_main_voltage", 30.0),
                                            "minimum_main_voltage": energy_data.get("minimum_main_voltage", 10.0),
                                            "nominal_main_voltage": energy_data.get("nominal_main_voltage", 12.0),
                                        }
                                        result["sources"] = energy_data.get("sources", [])
                                        if "trend" in energy_data:
                                            result["controller_trend"] = energy_data["trend"]
                                except Exception as e:
                                    _logger.warning(f"Error getting energy controller data from {proc.name}: {e}")
                            break
            
            # Try to get BatteryService data if available
            for proc in system.get_processes():
                if proc.state == "RUNNING":
                    for svc in proc.services:
                        if svc.rpc_service == "BatteryService":
                            endpoint_key = f"api/battery/{proc.name}"
                            service_collector = self._service_collector_cache.get(endpoint_key)
                            if service_collector:
                                try:
                                    battery_data = service_collector.get_data()
                                    if battery_data.get("ok"):
                                        battery_obj = {
                                            "instance": battery_data.get("instance", 0),
                                            "label": battery_data.get("label", "Battery_0"),
                                            "battery_data": {
                                                "voltage": battery_data.get("voltage", 0.0),
                                                "current": battery_data.get("current", 0.0),
                                                "power": battery_data.get("power", 0.0),
                                                "state_of_charge": battery_data.get("state_of_charge", 0.0),
                                                "energy": battery_data.get("energy", 0.0),
                                            },
                                            "trend": battery_data.get("trend", {"samples": []})
                                        }
                                        result["batteries"].append(battery_obj)
                                except Exception as e:
                                    _logger.warning(f"Error getting battery data from {proc.name}: {e}")
                            break
            
            return result
        
        except Exception as e:
            _logger.warning(f"Error in energy_status: {e}")
            return {
                "ok": True,
                "controller": {},
                "batteries": [],
                "sources": []
            }

    def is_energy_service_available(self) -> bool:
        """Check if EnergyService is available in any running process.
        
        Returns:
            bool: True if EnergyService is available, False otherwise
        """
        try:
            system = self._get_agent_status()
            if system is None:
                return False
            
            # Check if any running process has EnergyService
            for proc in system.get_processes():
                if proc.state == "RUNNING":
                    for svc in proc.services:
                        if svc.rpc_service == "EnergyService":
                            return True
            return False
        except Exception as e:
            _logger.warning(f"Error checking EnergyService availability: {e}")
            return False

    def set_global_configuration(self, config_name: str) -> dict:
        """Apply a global network configuration."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net_collector = self._get_network_collector()
            return net_collector.set_global_configuration(config_name)

    def network_interface_cmd(self, interface_name: str, connection_name: str, cmd: str) -> dict:
        """Send a command to a network interface (up, down, delete, add connection)."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net_collector = self._get_network_collector()
            return net_collector.interface_cmd(interface_name, connection_name, cmd)

    def nmea2000_status(self, process_name: str) -> dict:
        """Return the NMEA2000 controller status and devices for a process."""
        endpoint_key = f"api/nmea2000/{process_name}"
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"NMEA2000 service not available for {process_name}"}
        return service_collector.get_data()

    def nmea2000_device(self, process_name: str, device_address: int) -> dict:
        """Return detailed info for a single NMEA2000 device."""
        endpoint_key = f"api/nmea2000/{process_name}"
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"NMEA2000 service not available for {process_name}"}
        if hasattr(service_collector, 'get_device'):
            return service_collector.get_device(device_address)
        return {"ok": False, "error": "Device query not supported"}

    def nmea2000_pgn_definition(self, process_name: str, pgn: int) -> dict:
        """Return the PGN definition (description) for a given PGN."""
        endpoint_key = f"api/nmea2000/{process_name}"
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"NMEA2000 service not available for {process_name}"}
        if hasattr(service_collector, 'get_pgn_definition'):
            return service_collector.get_pgn_definition(pgn)
        return {"ok": False, "error": "PGN definition query not supported"}

    def nmea2000_trace_cmd(self, process_name: str, cmd: str) -> dict:
        """Send a trace command (start_trace/stop_trace) to the NMEA2000 service."""
        if cmd not in ("start_trace", "stop_trace"):
            return {"ok": False, "error": f"Unsupported NMEA2000 command: {cmd}"}
        endpoint_key = f"api/nmea2000/{process_name}"
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"NMEA2000 service not available for {process_name}"}
        if hasattr(service_collector, 'trace_cmd'):
            return service_collector.trace_cmd(cmd)
        return {"ok": False, "error": "Trace command not supported"}

    def mppt_status(self, process_name: str) -> dict:
        """Return the MPPT device info, parameters and live output for a process."""
        endpoint_key = f"api/mppt/{process_name}"
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"MPPT service not available for {process_name}"}
        return service_collector.get_data()

    def mppt_trend(self, process_name: str) -> dict:
        """Return the trailing solar output trend for an MPPT process."""
        endpoint_key = f"api/mppt/{process_name}"
        service_collector = self._service_collector_cache.get(endpoint_key)
        if service_collector is None:
            return {"ok": False, "error": f"MPPT service not available for {process_name}"}
        if hasattr(service_collector, 'get_trend'):
            return service_collector.get_trend()
        return {"ok": False, "error": "Trend query not supported"}
