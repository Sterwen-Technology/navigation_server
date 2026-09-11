#-------------------------------------------------------------------------------
# Name:        server
# Purpose:     Web interface for navigation_server, accessing gRPC servers
#
#              This module provides a lightweight HTTP server (based on the
#              standard library) that exposes a JSON API and a single-page web
#              frontend. It re-uses the existing gRPC clients (AgentClient,
#              ConsoleClient, NetworkClient) from navigation_server.router_common
#              and navigation_server.navigation_clients to access the
#              navigation_server gRPC services.
#
# Author:      Vibe Code
#
# Created:     15/08/2025
# Copyright:   (c) Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import queue
import secrets
import sys
import threading
import time
from abc import ABC, abstractmethod
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from navigation_server.router_common import GrpcClient, GrpcAccessException
from navigation_server.router_common.agent_interface import AgentClient
from navigation_server.router_common.global_variables import MessageServerGlobals
from navigation_server.navigation_clients import NetworkClient
from navigation_server.navigation_clients.console_client import ConsoleClient
from navigation_server.navigation_clients.n2k_can_client import NMEA2000CanClient
from navigation_server.navigation_clients.navigation_data_client import EngineClient
from navigation_server.navigation_clients.energy_client import MPPT_Client
from navigation_server.generated.network_pb2 import NetInterface as NetInterfacePb

_logger = logging.getLogger("ShipDataServer." + __name__)

# Path to the directory containing the static frontend assets (index.html ...).
# This allows the package to be installed as a wheel while still serving the
# frontend bundled alongside the Python module.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Default gRPC agent address, aligned with agent_cli.py default port 4545.
DEFAULT_GRPC_ADDRESS = "127.0.0.1"
DEFAULT_GRPC_PORT = 4545
DEFAULT_WEB_PORT = 4545
DEFAULT_WEB_HOST = "0.0.0.0"

# PBKDF2 parameters for web user password hashing (stdlib only, no deps).
_PBKDF2_ALGORITHM = "sha256"
_PBKDF2_ITERATIONS = 200_000
_PBKDF2_DKLEN = 32
# Lifetime of a session token, in seconds.
DEFAULT_SESSION_TIMEOUT = 3600
_SESSION_COOKIE = "navsession"


class UserStore:
    """File-backed store of web users.

    The credentials file holds one user per line as::

        username:base64(salt):base64(hash):iterations

    Passwords are never stored in clear text: only a PBKDF2-HMAC-SHA256
    hash (with an independent per-user salt) is persisted. The file itself
    lives on the device at a path set in the YAML configuration, so no
    secret is ever committed to the repository.

    ``UserStore`` is a low-level data layer: it loads, saves and looks up
    user records. Password verification and session management live in
    :class:`Authenticator`.
    """

    def __init__(self, credentials_file: str):
        self._path = credentials_file
        self._lock = threading.Lock()
        self._users = {}
        self._load()

    def _load(self):
        self._users = {}
        if not self._path or not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for lineno, raw in enumerate(f, 1):
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(":")
                    if len(parts) != 4:
                        _logger.warning("Ignored malformed line %d in %s",
                                        lineno, self._path)
                        continue
                    username, salt_b64, hash_b64, iters_s = parts
                    try:
                        salt = base64.b64decode(salt_b64)
                        digest = base64.b64decode(hash_b64)
                        iterations = int(iters_s)
                    except (ValueError, TypeError):
                        _logger.warning("Ignored undecodable line %d in %s",
                                        lineno, self._path)
                        continue
                    self._users[username] = (salt, digest, iterations)
        except OSError as err:
            _logger.error("Cannot read credentials file %s: %s", self._path, err)

    def save(self):
        with self._lock:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for username, (salt, digest, iterations) in self._users.items():
                    f.write("%s:%s:%s:%d\n" % (
                        username,
                        base64.b64encode(salt).decode("ascii"),
                        base64.b64encode(digest).decode("ascii"),
                        iterations,
                    ))
            os.replace(tmp, self._path)

    def has_user(self, username: str) -> bool:
        with self._lock:
            return username in self._users

    def list_users(self):
        with self._lock:
            return list(self._users.keys())

    def get(self, username: str):
        with self._lock:
            return self._users.get(username)

    def set(self, username: str, password: str, iterations: int = _PBKDF2_ITERATIONS):
        with self._lock:
            salt = os.urandom(16)
            digest = hashlib.pbkdf2_hmac(_PBKDF2_ALGORITHM,
                                         password.encode("utf-8"),
                                         salt, iterations, _PBKDF2_DKLEN)
            self._users[username] = (salt, digest, iterations)

    def delete(self, username: str) -> bool:
        with self._lock:
            if username not in self._users:
                return False
            del self._users[username]
            return True


class Authenticator:
    """Optional HTTP authentication for the web API.

    When enabled (``auth['enabled']`` in the web server YAML), every
    ``/api/*`` route except ``/api/login`` requires a valid session token
    delivered as an ``HttpOnly`` cookie. Authentication is entirely optional:
    when disabled (the default, or when the ``auth`` block is absent) the
    guard is a no-op and the server behaves exactly as before.

    The authenticator owns the session token store (in-memory, protected by a
    lock) and delegates password verification to a :class:`UserStore` backed by
    a device-local credentials file. No password is ever hardcoded in source
    or committed to the repository.
    """

    def __init__(self, store: UserStore, session_timeout: int = DEFAULT_SESSION_TIMEOUT,
                 enabled: bool = False):
        self._store = store
        self.enabled = enabled
        self._session_timeout = session_timeout
        self._sessions = {}  # token -> {username, expires_at}
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, auth_config: dict):
        """Build an Authenticator from the ``auth`` YAML dictionary.

        ``auth_config`` is the value of the ``auth`` key in the web server
        YAML section (or ``None`` when absent). Returns a disabled
        authenticator when the block is missing or ``enabled`` is false.
        """
        if not auth_config:
            return cls(enabled=False, store=_NullUserStore())
        enabled = bool(auth_config.get("enabled", False))
        credentials_file = auth_config.get("credentials_file")
        if not enabled or not credentials_file:
            return cls(enabled=False, store=_NullUserStore())
        if not os.path.isfile(credentials_file):
            _logger.error("Web authentication without credentials file: %s", credentials_file)
            return cls(enabled=False, store=_NullUserStore())
        timeout = int(auth_config.get("session_timeout", DEFAULT_SESSION_TIMEOUT))
        return cls(UserStore(credentials_file), session_timeout=timeout, enabled=enabled)

    def login(self, username: str, password: str) -> str | None:
        """Verify credentials and return a fresh session token, or ``None``."""
        record = self._store.get(username)
        if record is None:
            # Constant-time-ish failure: run a dummy derivation.
            hashlib.pbkdf2_hmac(_PBKDF2_ALGORITHM, password.encode("utf-8"),
                                b"\x00" * 16, _PBKDF2_ITERATIONS, _PBKDF2_DKLEN)
            return None
        salt, expected, iterations = record
        digest = hashlib.pbkdf2_hmac(_PBKDF2_ALGORITHM, password.encode("utf-8"),
                                     salt, iterations, _PBKDF2_DKLEN)
        if not hmac.compare_digest(digest, expected):
            return None
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {
                "username": username,
                "expires_at": time.time() + self._session_timeout,
            }
        return token

    def logout(self, token: str):
        with self._lock:
            self._sessions.pop(token, None)

    def is_valid(self, token: str) -> bool:
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return False
            if session["expires_at"] < time.time():
                del self._sessions[token]
                return False
            return True

    def check_request(self, handler) -> bool:
        """Return True if the request is authorized.

        When authentication is disabled this always returns True, preserving
        the historical open behaviour.
        """
        if not self.enabled:
            return True
        cookies = handler.headers.get("Cookie", "")
        token = None
        for part in cookies.split(";"):
            part = part.strip()
            if part.startswith(_SESSION_COOKIE + "="):
                token = part[len(_SESSION_COOKIE) + 1:]
                break
        return self.is_valid(token) if token else False

    @property
    def session_timeout(self) -> int:
        return self._session_timeout


class _NullUserStore(UserStore):
    """No-op store used when authentication is disabled."""

    def __init__(self):
        # Skip the file-backed initialiser entirely.
        self._path = None
        self._lock = threading.Lock()
        self._users = {}

    def _load(self):
        pass


class ProcessBox:
    """Manages data exchange with a single process and its services.
    
    This class handles the gRPC connection to a specific process and provides
    access to its services. It caches the connection and manages service clients.
    """
    
    def __init__(self, collector, process_name: str):
        self._collector = collector
        self._process_name = process_name
        self._port = None
        self._secure = None
        self._grpc_server = None
        self._services = {}  # service_type -> ServiceWindow instance
        self._services_definition = None  # Will contain the list of Service (from protobuf)
        self._lock = threading.Lock()
    
    @property
    def process_name(self) -> str:
        return self._process_name
    
    @property
    def port(self) -> int:
        if self._port is None:
            self._port = self._collector.get_process_port(self._process_name)
        return self._port
    
    @property
    def secure(self) -> bool:
        if self._secure is None:
            self._secure = self._collector.get_process_secure(self._process_name)
        return self._secure
    
    def get_grpc_server(self) -> "GrpcClient":
        """Get or create the gRPC server connection for this process."""
        if self._grpc_server is None or self._grpc_server.not_connected:
            with self._lock:
                if self._grpc_server is None or self._grpc_server.not_connected:
                    server_key = f"{self._collector.agent_host}:{self.port}"
                    self._grpc_server = GrpcClient.get_client(server_key, secure=self.secure)
                    self._grpc_server.connect()
                    self._grpc_server.wait_connect(5.0)
                    # now retrieve all services from the server (process)
                    self._services_definition = self._grpc_server.send_control_channel_command("SERVICES")
        return self._grpc_server
    
    def get_service(self, service_type: str, service_class):
        """Get or create a service window for this process.
        
        Args:
            service_type: The type of service (e.g., 'console', 'nmea2000', 'engine')
            service_class: The ServiceWindow subclass to instantiate
            
        Returns:
            ServiceWindow instance for the requested service
        """
        if service_type not in self._services:
            # Resolve the gRPC server outside the service lock: get_grpc_server()
            # holds its own lock, so nesting it under self._lock would deadlock
            # (threading.Lock is not reentrant).
            grpc_server = self.get_grpc_server()
            with self._lock:
                if service_type not in self._services:
                    service = service_class(self, grpc_server)
                    self._services[service_type] = service
        return self._services[service_type]

    @property
    def services(self):
        """The list of Service descriptors implemented by this process.

        Populated once when the process gRPC server is first connected via the
        control-channel SERVICES command, so callers can check which services a
        process exposes without re-querying the agent.
        """
        if self._services_definition is None:
            # Force connection, which retrieves the services definition.
            self.get_grpc_server()
        return self._services_definition or []

    def has_service(self, rpc_service: str) -> bool:
        """Return True if this process implements the given gRPC service."""
        return any(svc.rpc_service == rpc_service for svc in self.services)


class ServiceWindow(ABC):
    """Abstract base class for service windows.
    
    Each service (Console, NMEA2000, Engine, etc.) has its own subclass that
    implements the specific data retrieval and formatting methods.
    """
    
    def __init__(self, process_box: ProcessBox, grpc_server: GrpcClient):
        self._process_box = process_box
        self._grpc_server = grpc_server
        self._client = None
        self._initialized = False
    
    @property
    def process_name(self) -> str:
        return self._process_box.process_name
    
    @property
    def grpc_server(self) -> GrpcClient:
        return self._grpc_server
    
    def _ensure_client(self):
        """Ensure the gRPC client is initialized."""
        if not self._initialized:
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


class ConsoleServiceWindow(ServiceWindow):
    """Service window for Console service."""
    
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


class NMEA2000ServiceWindow(ServiceWindow):
    """Service window for NMEA2000 service."""
    
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


class EngineServiceWindow(ServiceWindow):
    """Service window for the EngineData service.

    The window caches the list of engine parameters (static engine definitions)
    retrieved once when the client is initialized, then serves both the engine
    list and the detailed engine data for each engine instance from that list.
    """
    
    def _initialize_client(self):
        self._client = EngineClient()
        self._grpc_server.add_service(self._client)
        # List of engine_parameters (static engine definitions) for this process.
        # Default to None before the call so that, if get_engines() raises, the
        # window is left in a safe (empty) state rather than missing the attribute.
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
        """ServiceWindow contract: return the engine list for this process."""
        try:
            return {"ok": True, "engines": self.get_engine_list()}
        except GrpcAccessException:
            return {"ok": False, "error": "Engine service unavailable"}


class MPPTServiceWindow(ServiceWindow):
    """Service window for the MPPT (solar charge controller) service.

    The window exposes three facets of an MPPT device:
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
            "battery": params.battery,
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
            return {
                "ok": True,
                "process": self.process_name,
                "id": device._device.id,
                "device_label": device._device.device_label,
                "device_model": device._device.device_model,
                "product_id": device.product_id,
                "firmware": device.firmware,
                "serial": device.serial,
                "error": device.error,
                "state": device.state,
                "mppt_state": device.mppt_state,
                "day_max_power": round(device.day_max_power, 1),
                "day_power": round(device.day_yield, 3),
                "msg_timestamp": device._device.msg_timestamp,
                "parameters": self._parameters_dict(device._device.parameters),
                "output": {
                    "panel_voltage": round(output.panel_voltage, 2),
                    "voltage": round(output.voltage, 2),
                    "current": round(output.current, 2),
                    "panel_power": round(output.panel_power, 1),
                },
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


class NavigationSystemCollector:
    """Wraps the gRPC AgentClient and exposes a plain-dict view of the system.

    The collector holds the connection to a single gRPC agent server and lazily
    instantiates the service clients (Agent, Console, Network). All returned data
    is serialisable JSON (no protobuf objects leak to the HTTP layer).
    
    Uses ProcessBox to manage per-process connections and ServiceWindow subclasses
    for each service type (Console, NMEA2000, Engine, etc.).
    """

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
        self._network = None
        self._process_boxes = {}  # process_name -> ProcessBox
        self._lock = threading.Lock()

    @property
    def agent_address(self) -> str:
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
        return self._server.state

    def _process_descriptor(self, process_name: str):
        """Return the SystemProcessMsgProxy for a process, or None.

        Looks up the process in the current agent status. Used by the formal
        per-process accessors below so callers never reach into the agent or
        the process boxes' private state.
        """
        system = self._agent.system_cmd("status")
        if system is None:
            return None
        for proc in system.get_processes():
            if proc.name == process_name:
                return proc
        return None

    def get_process_port(self, process_name: str) -> int:
        """Return the gRPC port declared by a process (0 if unknown)."""
        proc = self._process_descriptor(process_name)
        return proc.grpc_port if proc is not None else 0

    def get_process_secure(self, process_name: str) -> bool:
        """Return whether a process expects secure gRPC."""
        proc = self._process_descriptor(process_name)
        return bool(proc.secure_grpc) if proc is not None else False

    def _ensure_network(self):
        if self._network is None:
            self._network = NetworkClient()
            self._server.add_service(self._network)
        return self._network


    def _get_process_box(self, process_name: str) -> "ProcessBox":
        """Get or create a ProcessBox for a process."""
        if process_name not in self._process_boxes:
            self._process_boxes[process_name] = ProcessBox(self, process_name)
        return self._process_boxes[process_name]

    def _get_service_window(self, process_name: str, service_type: str, service_class):
        """Get or create a ServiceWindow for a process and service type.

        The ServiceWindow cache is owned by the ProcessBox, which is the single
        authority for a process's service windows.
        """
        process_box = self._get_process_box(process_name)
        return process_box.get_service(service_type, service_class)

    def console_status(self, process_name: str) -> dict:
        """Return the console view (servers + couplers) of a process."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            try:
                service_window = self._get_service_window(process_name, 'console', ConsoleServiceWindow)
                return service_window.get_data()
            except Exception as e:
                return {"ok": False, "error": f"Console service error: {str(e)}"}

    def coupler_cmd(self, process_name: str, coupler_name: str, cmd: str) -> dict:
        """Send a command to a coupler on a process console."""
        allowed = ("start", "stop", "start_trace_raw", "stop_trace", "suspend", "resume")
        if cmd not in allowed:
            return {"ok": False, "error": f"Unsupported coupler command: {cmd}"}
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            try:
                service_window = self._get_service_window(process_name, 'console', ConsoleServiceWindow)
                return service_window.coupler_cmd(coupler_name, cmd)
            except Exception as e:
                return {"ok": False, "error": f"Coupler command error: {str(e)}"}

    def _connect(self):
        if self._server.not_connected:
            self._server.connect()
            self._server.wait_connect(5.0)

    def system_status(self) -> dict:
        """Return the full navigation system status as a JSON-serialisable dict."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {
                    "connected": False,
                    "agent_address": self.agent_address,
                    "error": "Agent gRPC server unreachable",
                }
            system = self._agent.system_cmd("status")
            if system is None:
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

    @staticmethod
    def _system_to_dict(system) -> dict:
        """Convert a NavigationSystemMsgProxy into a plain dict."""
        processes = []
        for proc in system.get_processes():
            servers = []
            for server in proc.servers:
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
            services_list = [
                {
                    "service_name": service.service_name,
                    "rpc_service": service.rpc_service,
                }
                for service in proc.services
            ]
            processes.append({
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
                "servers": servers,
                "services": services_list,
            })
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
        if cmd not in ("start", "stop", "restart"):
            return {"ok": False, "error": f"Unsupported command: {cmd}"}
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            resp = self._agent.process_cmd(cmd, target)
            if resp is None:
                return {"ok": False, "error": f"Command '{cmd}' failed on {target}"}
            return {"ok": True, "response": resp.response}

    def system_cmd(self, cmd: str) -> dict:
        """Send a system command (halt/reboot/navigation_restart) to the agent."""
        if cmd not in ("halt", "reboot", "navigation_restart"):
            return {"ok": False, "error": f"Unsupported system command: {cmd}"}
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            err = self._agent.system_cmd(cmd)
            if err is None:
                return {"ok": False, "error": f"System command '{cmd}' failed"}
            return {"ok": True, "err_code": err}

    def start_log_stream(self, process_name: str, line_callback) -> bool:
        """Start streaming logs for a process via the agent GetSystemLog.

        Uses the callback-based streaming reader (non-blocking). The
        line_callback is invoked for each received log line. Only one log
        stream can be active at a time (agent limitation).
        """
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return False
        try:
            self._agent.get_log(process_name, line_callback)
        except GrpcAccessException:
            _logger.error(f"Error starting log stream for {process_name}")
            return False
        return True

    def stop_log_stream(self):
        """Stop the active log stream."""
        self._agent.stop_log()

    def network_status(self) -> dict:
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net = self._ensure_network()
            try:
                status = net.network_status("update")
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

    def network_configurations(self) -> dict:
        """Return the available global network configurations."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net = self._ensure_network()
            try:
                reply = net.get_global_configuration()
            except GrpcAccessException:
                return {"ok": False, "error": "Network service unavailable"}
            return {"ok": True, "configurations": reply.configuration_names()}

    def network_connection_definitions(self) -> dict:
        """Return the available connection names (configuration names)."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net = self._ensure_network()
            try:
                reply = net.get_global_configuration()
            except GrpcAccessException:
                return {"ok": False, "error": "Network service unavailable"}
            return {"ok": True, "connections": reply.configuration_names()}

    def _engine_processes(self):
        """Yield process names exposing the EngineData service.

        Process membership and service list come from the agent status, which is
        the authoritative registry of registered processes. The per-process
        EngineServiceWindow (built on demand) then caches the engine list.
        """
        system = self._agent.system_cmd("status")
        if system is None:
            return
        for proc in system.get_processes():
            if any(svc.rpc_service == "EngineData" for svc in proc.services):
                yield proc.name

    def engine_list(self) -> dict:
        """Return the list of available engines across processes with EngineData.

        Each process with an EngineData service is served by an
        EngineServiceWindow that caches its engine parameters; the window's
        get_engine_list() produces the summaries (with live runtime data).
        """
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            engines = []
            for process_name in self._engine_processes():
                try:
                    window = self._get_service_window(process_name, 'engine', EngineServiceWindow)
                    engines.extend(window.get_engine_list())
                except Exception as e:
                    _logger.warning(f"Error retrieving engine list from {process_name}: {e}")
            return {"ok": True, "engines": engines}

    def engine_data(self, engine_id: int) -> dict:
        """Return detailed data for a specific engine instance.

        Iterates processes with an EngineData service and returns the first one
        able to serve the requested engine instance via its EngineServiceWindow.
        """
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            for process_name in self._engine_processes():
                try:
                    window = self._get_service_window(process_name, 'engine', EngineServiceWindow)
                    result = window.get_engine_data(engine_id)
                    if result.get("ok"):
                        return result
                except Exception as e:
                    _logger.warning(f"Error getting engine data from {process_name}: {e}")
                    continue
            return {"ok": False, "error": f"Engine {engine_id} not found or no process with EngineData service"}

    def set_global_configuration(self, config_name: str) -> dict:
        """Apply a global network configuration."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net = self._ensure_network()
            try:
                net.set_global_configuration(config_name)
            except GrpcAccessException:
                return {"ok": False, "error": "Network service unavailable"}
            return {"ok": True, "configuration": config_name}

    def network_interface_cmd(self, interface_name: str, connection_name: str, cmd: str) -> dict:
        """Send a command to a network interface (up, down, delete, add connection)."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            net = self._ensure_network()
            try:
                if cmd == "add":
                    # Add a connection to an interface
                    iface_pb = NetInterfacePb()
                    iface_pb.name = interface_name
                    result = net.set_configuration("add", connection_name, iface_pb)
                else:
                    # For up, down, delete commands
                    iface_pb = NetInterfacePb()
                    iface_pb.name = interface_name
                    result = net.interface_command(cmd, iface_pb)
            except GrpcAccessException:
                return {"ok": False, "error": "Network service unavailable"}
            return {
                "ok": True,
                "status": result.status,
                "details": result.details,
            }

    def nmea2000_status(self, process_name: str) -> dict:
        """Return the NMEA2000 controller status and devices for a process."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            try:
                service_window = self._get_service_window(process_name, 'nmea2000', NMEA2000ServiceWindow)
                return service_window.get_data()
            except Exception as e:
                return {"ok": False, "error": f"NMEA2000 service error: {str(e)}"}

    def nmea2000_device(self, process_name: str, device_address: int) -> dict:
        """Return detailed info for a single NMEA2000 device."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            try:
                service_window = self._get_service_window(process_name, 'nmea2000', NMEA2000ServiceWindow)
                return service_window.get_device(device_address)
            except Exception as e:
                return {"ok": False, "error": f"NMEA2000 device error: {str(e)}"}

    def nmea2000_pgn_definition(self, process_name: str, pgn: int) -> dict:
        """Return the PGN definition (description) for a given PGN."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            try:
                service_window = self._get_service_window(process_name, 'nmea2000', NMEA2000ServiceWindow)
                return service_window.get_pgn_definition(pgn)
            except Exception as e:
                return {"ok": False, "error": f"NMEA2000 PGN definition error: {str(e)}"}

    def nmea2000_trace_cmd(self, process_name: str, cmd: str) -> dict:
        """Send a trace command (start_trace/stop_trace) to the NMEA2000 service."""
        if cmd not in ("start_trace", "stop_trace"):
            return {"ok": False, "error": f"Unsupported NMEA2000 command: {cmd}"}
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            try:
                service_window = self._get_service_window(process_name, 'nmea2000', NMEA2000ServiceWindow)
                return service_window.trace_cmd(cmd)
            except Exception as e:
                return {"ok": False, "error": f"NMEA2000 trace error: {str(e)}"}

    def _mppt_processes(self):
        """Yield process names exposing the MPPTService service."""
        system = self._agent.system_cmd("status")
        if system is None:
            return
        for proc in system.get_processes():
            if any(svc.rpc_service == "MPPTService" for svc in proc.services):
                yield proc.name

    def mppt_status(self, process_name: str) -> dict:
        """Return the MPPT device info, parameters and live output for a process."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            try:
                service_window = self._get_service_window(process_name, 'mppt', MPPTServiceWindow)
                return service_window.get_data()
            except Exception as e:
                return {"ok": False, "error": f"MPPT service error: {str(e)}"}

    def mppt_trend(self, process_name: str) -> dict:
        """Return the trailing solar output trend for an MPPT process."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            try:
                service_window = self._get_service_window(process_name, 'mppt', MPPTServiceWindow)
                return service_window.get_trend()
            except Exception as e:
                return {"ok": False, "error": f"MPPT trend error: {str(e)}"}


def _validate_coupler_cmd(cmd: str, state: str) -> tuple:
    """Validate that a coupler command is consistent with its current state.

    Returns (True, "") if valid, (False, reason) otherwise.
    """
    running = state == "RUNNING"
    suspended = state == "SUSPENDED"
    active = running or suspended
    if cmd == "start" and active:
        return False, "coupler is already active"
    if cmd == "stop" and not active:
        return False, "coupler is not active"
    if cmd == "suspend" and not running:
        return False, "coupler is not running"
    if cmd == "resume" and not suspended:
        return False, "coupler is not suspended"
    # trace commands: start_trace_raw requires the coupler to be active,
    # stop_trace requires it to be running (tracing implies running)
    if cmd == "start_trace_raw" and not active:
        return False, "coupler is not active"
    if cmd == "stop_trace" and not running:
        return False, "coupler is not running"
    return True, ""



class _RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler serving the JSON API and the static frontend."""

    # Shared collector set by NavigationWebServer before serving.
    collector: NavigationSystemCollector = None
    web_server = None  # type: NavigationWebServer | None
    authenticator = None  # type: Authenticator | None

    server_version = "NavigationWebServer/1.0"

    def log_message(self, format, *args):  # noqa: A002 - signature from stdlib
        _logger.info("%s - %s" % (self.address_string(), format % args))

    # --- routing -----------------------------------------------------------
    def do_GET(self):  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._serve_static("index.html", "text/html; charset=utf-8")
        elif path == "/api/login":
            self._serve_login_status()
        elif not self._authorized(path):
            self._unauthorized()
        elif path == "/api/status":
            self._serve_json(self.collector.system_status())
        elif path == "/api/network":
            self._serve_json(self.collector.network_status())
        elif path == "/api/network/configs":
            self._serve_json(self.collector.network_configurations())
        elif path == "/api/network/connections":
            self._serve_json(self.collector.network_connection_definitions())
        elif path == "/api/engines":
            self._serve_json(self.collector.engine_list())
        elif path.startswith("/api/engine/"):
            engine_id_str = path[len("/api/engine/"):]
            try:
                engine_id = int(engine_id_str)
                self._serve_json(self.collector.engine_data(engine_id))
            except ValueError:
                self._serve_json({"ok": False, "error": "invalid engine ID"}, status=HTTPStatus.BAD_REQUEST)
        elif path.startswith("/api/log/stream/"):
            process_name = path[len("/api/log/stream/"):]
            if process_name:
                self._serve_log_stream(process_name)
            else:
                self._serve_json({"ok": False, "error": "missing process name"},
                                 status=HTTPStatus.BAD_REQUEST)
        elif path.startswith("/api/console/"):
            process_name = path[len("/api/console/"):]
            if process_name:
                self._serve_json(self.collector.console_status(process_name))
            else:
                self._serve_json({"ok": False, "error": "missing process name"},
                                 status=HTTPStatus.BAD_REQUEST)
        elif path.startswith("/api/mppt/"):
            parts = path[len("/api/mppt/"):].split("/")
            if len(parts) == 1 and parts[0]:
                self._serve_json(self.collector.mppt_status(parts[0]))
            elif len(parts) == 2 and parts[0] and parts[1] == "trend":
                self._serve_json(self.collector.mppt_trend(parts[0]))
            else:
                self._serve_json({"ok": False, "error": "invalid MPPT path"},
                                 status=HTTPStatus.BAD_REQUEST)
        elif path == "/api/config":
            self._serve_config()
        elif path == "/health":
            self._serve_json({"ok": True, "time": time.time()})
        elif path.startswith("/api/nmea2000/"):
            parts = path[len("/api/nmea2000/"):].split("/")
            if len(parts) >= 1:
                process_name = parts[0]
                if len(parts) == 2 and parts[1] == "status":
                    self._serve_json(self.collector.nmea2000_status(process_name))
                elif len(parts) == 4 and parts[1] == "device" and parts[3] == "pgn":
                    try:
                        pgn = int(parts[2])
                        self._serve_json(self.collector.nmea2000_pgn_definition(process_name, pgn))
                    except ValueError:
                        self._serve_json({"ok": False, "error": "invalid device address or PGN"},
                                         status=HTTPStatus.BAD_REQUEST)
                elif len(parts) == 3 and parts[1] == "device":
                    try:
                        device_address = int(parts[2])
                        self._serve_json(self.collector.nmea2000_device(process_name, device_address))
                    except ValueError:
                        self._serve_json({"ok": False, "error": "invalid device address"},
                                         status=HTTPStatus.BAD_REQUEST)
                else:
                    self._serve_json({"ok": False, "error": "invalid NMEA2000 path"},
                                     status=HTTPStatus.BAD_REQUEST)
            else:
                self._serve_json({"ok": False, "error": "missing process name"},
                                 status=HTTPStatus.BAD_REQUEST)
        else:
            self._serve_static(path.lstrip("/"))

    def do_POST(self):  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        if path == "/api/login":
            self._handle_login()
            return
        if path == "/api/logout":
            self._handle_logout()
            return
        if not self._authorized(path):
            self._unauthorized()
            return
        body = self._read_json_body()
        if body is None:
            return
        if path == "/api/process":
            target = body.get("target")
            cmd = body.get("cmd")
            if not target or not cmd:
                self._serve_json({"ok": False, "error": "missing 'target' or 'cmd'"},
                                 status=HTTPStatus.BAD_REQUEST)
                return
            self._serve_json(self.collector.process_cmd(cmd, target))
        elif path == "/api/system":
            cmd = body.get("cmd")
            if not cmd:
                self._serve_json({"ok": False, "error": "missing 'cmd'"},
                                 status=HTTPStatus.BAD_REQUEST)
                return
            self._serve_json(self.collector.system_cmd(cmd))
        elif path == "/api/network/config":
            config_name = body.get("configuration")
            if not config_name:
                self._serve_json({"ok": False, "error": "missing 'configuration'"},
                                 status=HTTPStatus.BAD_REQUEST)
                return
            self._serve_json(self.collector.set_global_configuration(config_name))
        elif path == "/api/network/interface":
            interface_name = body.get("interface")
            connection_name = body.get("connection")
            cmd = body.get("cmd")
            if not interface_name or not cmd:
                self._serve_json({"ok": False, "error": "missing 'interface' or 'cmd'"},
                                 status=HTTPStatus.BAD_REQUEST)
                return
            self._serve_json(self.collector.network_interface_cmd(interface_name, connection_name, cmd))
        elif path == "/api/log/stop":
            self.collector.stop_log_stream()
            self._serve_json({"ok": True})
        elif path == "/api/coupler":
            process = body.get("process")
            coupler = body.get("coupler")
            cmd = body.get("cmd")
            if not process or not coupler or not cmd:
                self._serve_json({"ok": False, "error": "missing 'process', 'coupler' or 'cmd'"},
                                 status=HTTPStatus.BAD_REQUEST)
                return
            self._serve_json(self.collector.coupler_cmd(process, coupler, cmd))
        elif path.startswith("/api/nmea2000/"):
            parts = path[len("/api/nmea2000/"):].split("/")
            if len(parts) >= 2 and parts[1] == "trace":
                process_name = parts[0]
                cmd = body.get("cmd")
                if not cmd:
                    self._serve_json({"ok": False, "error": "missing 'cmd'"},
                                     status=HTTPStatus.BAD_REQUEST)
                    return
                self._serve_json(self.collector.nmea2000_trace_cmd(process_name, cmd))
            else:
                self._serve_json({"ok": False, "error": "invalid NMEA2000 trace path"},
                                 status=HTTPStatus.BAD_REQUEST)
        else:
            self._serve_json({"ok": False, "error": "not found"},
                             status=HTTPStatus.NOT_FOUND)

    # --- helpers -----------------------------------------------------------
    # Authentication helpers. _RequestHandler holds an Authenticator (which
    # may be disabled). The guard is the single chokepoint for every /api
    # route; the login/logout endpoints are deliberately excluded from it.

    # Paths accessible without a session even when auth is enabled.
    _PUBLIC_API_PATHS = frozenset({"/api/login", "/api/logout", "/api/config",
                                   "/health"})

    def _authorized(self, path: str) -> bool:
        if not path.startswith("/api/"):
            return True
        if path in self._PUBLIC_API_PATHS:
            return True
        return self.authenticator.check_request(self)

    def _unauthorized(self):
        self._serve_json({"ok": False, "error": "unauthorized"},
                         status=HTTPStatus.UNAUTHORIZED)

    def _serve_login_status(self):
        self._serve_json({"ok": True, "auth_required": self.authenticator.enabled})

    def _handle_login(self):
        body = self._read_json_body()
        if body is None:
            return
        username = body.get("username")
        password = body.get("password")
        if not username or not password:
            self._serve_json({"ok": False, "error": "missing credentials"},
                             status=HTTPStatus.BAD_REQUEST)
            return
        token = self.authenticator.login(username, password)
        if token is None:
            self._serve_json({"ok": False, "error": "invalid credentials"},
                             status=HTTPStatus.UNAUTHORIZED)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie",
                         f"{_SESSION_COOKIE}={token}; HttpOnly; SameSite=Strict; "
                         f"Path=/; Max-Age={self.authenticator.session_timeout}")
        data = json.dumps({"ok": True, "username": username}).encode("utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_logout(self):
        self.authenticator.logout(self._extract_session_token())
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie",
                         f"{_SESSION_COOKIE}=; HttpOnly; SameSite=Strict; "
                         "Path=/; Max-Age=0")
        data = json.dumps({"ok": True}).encode("utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _extract_session_token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            part = part.strip()
            if part.startswith(_SESSION_COOKIE + "="):
                return part[len(_SESSION_COOKIE) + 1:]
        return None

    def _serve_json(self, payload: dict, status: int = HTTPStatus.OK):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_log_stream(self, process_name: str):
        """Stream log lines to the client via Server-Sent Events (SSE).

        The gRPC log stream is started with a callback that pushes each line
        as an SSE event. The connection stays open until the client
        disconnects or the stream ends.
        """
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        line_queue = queue.Queue(maxsize=200)
        client_disconnected = [False]

        def on_line(msg):
            try:
                # msg is a LogLines protobuf; extract the line string
                line_text = msg.line if hasattr(msg, 'line') else str(msg)
                line_queue.put_nowait(line_text)
            except queue.Full:
                pass

        # Start the gRPC log stream
        started = self.collector.start_log_stream(process_name, on_line)
        if not started:
            self.wfile.write(b"event: error\ndata: Cannot start log stream\n\n")
            self.wfile.flush()
            return

        self.wfile.write(b"event: started\ndata: ok\n\n")
        self.wfile.flush()

        try:
            while not client_disconnected[0]:
                try:
                    line = line_queue.get(timeout=1.0)
                    # SSE format: escape newlines in the data
                    data = line.replace("\n", "\ndata: ")
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Send a keepalive comment
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            client_disconnected[0] = True
        finally:
            self.collector.stop_log_stream()

    def _serve_static(self, relative_path: str, content_type: str = None):
        # Guard against path traversal.
        if ".." in relative_path:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        full_path = os.path.normpath(os.path.join(_STATIC_DIR, relative_path))
        if not full_path.startswith(os.path.abspath(_STATIC_DIR)):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not os.path.isfile(full_path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if content_type is None:
            content_type = _guess_mime(full_path)
        try:
            with open(full_path, "rb") as f:
                data = f.read()
        except OSError as err:
            _logger.error(f"Error reading static file {full_path}: {err}")
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(data)


    def _serve_config(self):
        """Serve the language configuration from the server."""
        try:
            config = {
                "version": MessageServerGlobals.version or "3.0.0"
            }
            # Try to get the actual language from configuration
            if MessageServerGlobals.configuration:
                language = MessageServerGlobals.configuration.get_option('language', "en")
                config["language"] = language
            else:
                # Fallback to collector's language
                config["language"] = self.collector.language
            self._serve_json(config)
        except Exception as e:
            _logger.error("Error serving config: %s", e)
            self._serve_json({"language": "en", "version": "3.0.0"})
    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            self._serve_json({"ok": False, "error": "empty body"},
                             status=HTTPStatus.BAD_REQUEST)
            return None
        try:
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            self._serve_json({"ok": False, "error": f"invalid JSON: {err}"},
                             status=HTTPStatus.BAD_REQUEST)
            return None


def _guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }.get(ext, "application/octet-stream")


class NavigationWebServer:
    """HTTP server exposing the navigation_server gRPC services as a web UI."""

    def __init__(self, host: str, port: int, grpc_address: str, grpc_port: int,
                 secure: bool = False, language: str = "en",
                 auth: Authenticator | None = None):
        self._host = host
        self._port = port
        self._language = language
        self._authenticator = auth or Authenticator(enabled=False, store=_NullUserStore())
        self._collector = NavigationSystemCollector(grpc_address, grpc_port, secure, language)
        # The request handler is re-instantiated per connection; expose the
        # collector and authenticator through a subclass so each handler has
        # access to them.
        handler_cls = type("BoundRequestHandler", (_RequestHandler,),
                           {"collector": self._collector, "web_server": self,
                            "authenticator": self._authenticator})
        self._httpd = ThreadingHTTPServer((host, port), handler_cls)

    def serve_forever(self):
        _logger.info(f"Navigation web server listening on http://{self._host}:{self._port}")
        _logger.info(f"Connecting to gRPC agent at {self._collector.agent_address} "
                     f"(secure={self._collector.secure})")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            _logger.info("Navigation web server stopping (KeyboardInterrupt)")
            self._httpd.shutdown()
        finally:
            self._httpd.server_close()

    def stop(self):
        self._httpd.shutdown()


def _load_certificate(path: str) -> bool:
    """Load a CA certificate for secure gRPC communication. Returns success."""
    try:
        with open(path, "rb") as f:
            certificate = f.read()
        GrpcClient.set_ca_certificate(certificate)
        return True
    except (FileNotFoundError, IOError) as err:
        _logger.error(f"Cannot load certificate {path}: {err}")
        return False


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Navigation server web interface")
    p.add_argument("-a", "--address", default=DEFAULT_WEB_HOST,
                   help=f"Web server bind address, default {DEFAULT_WEB_HOST}")
    p.add_argument("-p", "--port", type=int, default=DEFAULT_WEB_PORT,
                   help=f"Web server listening port, default {DEFAULT_WEB_PORT}")
    p.add_argument("-ga", "--grpc-address", default=DEFAULT_GRPC_ADDRESS,
                   help=f"gRPC agent address, default {DEFAULT_GRPC_ADDRESS}")
    p.add_argument("-gp", "--grpc-port", type=int, default=DEFAULT_GRPC_PORT,
                   help=f"gRPC agent port, default {DEFAULT_GRPC_PORT}")
    p.add_argument("-c", "--certificate", default=None,
                   help="CA certificate file for secure gRPC, default None")
    p.add_argument("-ns", "--no-sec", action="store_true", default=False,
                   help="Disable secure gRPC communication")
    p.add_argument("-v", "--verbose", action="store_true", default=False,
                   help="Verbose mode (info logging)")
    p.add_argument("-d", "--debug", action="store_true", default=False,
                   help="Debug mode (debug logging)")
    p.add_argument("--auth-file", default=None,
                   help="Credentials file enabling web API authentication")
    p.add_argument("--session-timeout", type=int, default=DEFAULT_SESSION_TIMEOUT,
                   help=f"Session lifetime in seconds, default {DEFAULT_SESSION_TIMEOUT}")
    return p


def web_main(argv=None):
    parser = _parser()
    options = parser.parse_args(argv)

    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s"))
    _logger.addHandler(log_handler)
    if options.debug:
        _logger.setLevel(logging.DEBUG)
    elif options.verbose:
        _logger.setLevel(logging.INFO)
    else:
        _logger.setLevel(logging.WARNING)

    secure = False
    if not options.no_sec:
        if options.certificate is None:
            cert_dir = os.getenv("NAV_CONF_DIR") or os.getenv("HOME")
            default_cert = os.path.join(cert_dir, "certificates", "nav_ca_cert.pem")
            if os.path.exists(default_cert):
                _logger.info(f"Using default certificate file: {default_cert}")
                options.certificate = default_cert
            else:
                _logger.warning(f"No default certificate file: {default_cert}")
        if options.certificate is not None:
            secure = _load_certificate(options.certificate)

    authenticator = Authenticator(enabled=False, store=_NullUserStore())
    if options.auth_file:
        authenticator = Authenticator(UserStore(options.auth_file),
                                       session_timeout=options.session_timeout,
                                       enabled=True)
        _logger.info("Web API authentication enabled (file=%s)" % options.auth_file)

    server = NavigationWebServer(
        host=options.address,
        port=options.port,
        grpc_address=options.grpc_address,
        grpc_port=options.grpc_port,
        secure=secure,
        auth=authenticator,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(web_main())
