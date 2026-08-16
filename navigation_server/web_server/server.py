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
import json
import logging
import os
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from navigation_server.router_common import GrpcClient, GrpcAccessException
from navigation_server.router_common.agent_interface import AgentClient
from navigation_server.navigation_clients import NetworkClient
from navigation_server.navigation_clients.console_client import ConsoleClient

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


class NavigationSystemCollector:
    """Wraps the gRPC AgentClient and exposes a plain-dict view of the system.

    The collector holds the connection to a single gRPC agent server and lazily
    instantiates the service clients (Agent, Console, Network). All returned data
    is serialisable JSON (no protobuf objects leak to the HTTP layer).
    """

    def __init__(self, address: str, port: int, secure: bool = False):
        self._address = address
        self._port = port
        self._secure = secure
        # The security mode (and CA certificate, shared at class level) applies
        # to the agent and to all console connections, since all gRPC servers in
        # a deployment share the same certificate.
        self._server = GrpcClient.get_client(f"{address}:{port}", secure=secure)
        self._agent = AgentClient()
        self._server.add_service(self._agent)
        self._network = None
        self._consoles = {}
        self._lock = threading.Lock()

    @property
    def agent_address(self) -> str:
        return f"{self._address}:{self._port}"

    @property
    def server_state(self) -> int:
        return self._server.state

    def _ensure_network(self):
        if self._network is None:
            self._network = NetworkClient()
            self._server.add_service(self._network)
        return self._network

    def _get_console(self, process_name: str):
        """Return a (GrpcClient, ConsoleClient) pair for a process console.

        The connection is cached per process name so that repeated calls
        (status refresh, coupler commands) reuse the same gRPC channel
        instead of creating a new one each time. The channel is only
        reconnected if it has dropped to NOT_CONNECTED.
        """
        cached = self._consoles.get(process_name)
        if cached is not None:
            grpc_server, console = cached
            # Reconnect only if the channel has dropped.
            if grpc_server.not_connected:
                grpc_server.connect()
                grpc_server.wait_connect(5.0)
            return cached
        port = self._agent.get_port(process_name)
        if port == 0:
            return None, None
        server_key = f"{self._address}:{port}"
        grpc_server = GrpcClient.get_client(server_key, secure=self._secure)
        console = ConsoleClient()
        grpc_server.add_service(console)
        grpc_server.connect()
        grpc_server.wait_connect(5.0)
        pair = (grpc_server, console)
        self._consoles[process_name] = pair
        return pair

    def console_status(self, process_name: str) -> dict:
        """Return the console view (servers + couplers) of a process."""
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            grpc_server, console = self._get_console(process_name)
            if grpc_server is None:
                return {"ok": False, "error": f"No console for process {process_name}"}
            if grpc_server.not_connected:
                return {"ok": False, "error": f"Cannot reach console for {process_name}"}
            # server status (SystemProcessMsg with TCP/UDP servers + connections)
            try:
                status = console.server_status()
            except GrpcAccessException:
                return {"ok": False, "error": "Console ServerStatus call failed"}
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
            # couplers
            couplers = []
            try:
                for c in console.get_couplers():
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
                return {"ok": False, "error": "Console GetCouplers call failed"}
            return {
                "ok": True,
                "process": process_name,
                "grpc_port": grpc_server.address.rsplit(":", 1)[-1] if ":" in grpc_server.address else 0,
                "servers": servers,
                "couplers": couplers,
            }

    def coupler_cmd(self, process_name: str, coupler_name: str, cmd: str) -> dict:
        """Send a command to a coupler on a process console."""
        allowed = ("start", "stop", "start_trace_raw", "stop_trace", "suspend", "resume")
        if cmd not in allowed:
            return {"ok": False, "error": f"Unsupported coupler command: {cmd}"}
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            grpc_server, console = self._get_console(process_name)
            if grpc_server is None:
                return {"ok": False, "error": f"No console for process {process_name}"}
            if grpc_server.not_connected:
                return {"ok": False, "error": f"Cannot reach console for {process_name}"}
            # Fetch the current coupler state to validate the command.
            try:
                coupler = console.get_coupler(coupler_name)
            except GrpcAccessException:
                return {"ok": False, "error": "Console GetCoupler call failed"}
            state = coupler.state
            # Check command consistency with the actual coupler state.
            valid = _validate_coupler_cmd(cmd, state)
            if not valid[0]:
                return {"ok": False, "error": f"Cannot '{cmd}' coupler {coupler_name} "
                                              f"(state={state}): {valid[1]}"}
            try:
                if cmd == "start":
                    # start uses a different console RPC than the other coupler commands
                    result = console.server_cmd("start_coupler", coupler_name)
                else:
                    result = console.send_cmd(coupler_name, cmd)
            except GrpcAccessException:
                return {"ok": False, "error": "Console command call failed"}
            return {"ok": True, "response": result, "state": state}

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
            processes.append({
                "id": proc.id,
                "name": proc.name,
                "state": proc.state,
                "grpc_port": proc.grpc_port,
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
        """Send a system command (halt/reboot) to the agent."""
        if cmd not in ("halt", "reboot"):
            return {"ok": False, "error": f"Unsupported system command: {cmd}"}
        with self._lock:
            self._connect()
            if self._server.not_connected:
                return {"ok": False, "error": "Agent gRPC server unreachable"}
            err = self._agent.system_cmd(cmd)
            if err is None:
                return {"ok": False, "error": f"System command '{cmd}' failed"}
            return {"ok": True, "err_code": err}

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

    server_version = "NavigationWebServer/1.0"

    def log_message(self, format, *args):  # noqa: A002 - signature from stdlib
        _logger.info("%s - %s" % (self.address_string(), format % args))

    # --- routing -----------------------------------------------------------
    def do_GET(self):  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._serve_static("index.html", "text/html; charset=utf-8")
        elif path == "/api/status":
            self._serve_json(self.collector.system_status())
        elif path == "/api/network":
            self._serve_json(self.collector.network_status())
        elif path.startswith("/api/console/"):
            process_name = path[len("/api/console/"):]
            if process_name:
                self._serve_json(self.collector.console_status(process_name))
            else:
                self._serve_json({"ok": False, "error": "missing process name"},
                                 status=HTTPStatus.BAD_REQUEST)
        elif path == "/health":
            self._serve_json({"ok": True, "time": time.time()})
        else:
            self._serve_static(path.lstrip("/"))

    def do_POST(self):  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
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
        elif path == "/api/coupler":
            process = body.get("process")
            coupler = body.get("coupler")
            cmd = body.get("cmd")
            if not process or not coupler or not cmd:
                self._serve_json({"ok": False, "error": "missing 'process', 'coupler' or 'cmd'"},
                                 status=HTTPStatus.BAD_REQUEST)
                return
            self._serve_json(self.collector.coupler_cmd(process, coupler, cmd))
        else:
            self._serve_json({"ok": False, "error": "not found"},
                             status=HTTPStatus.NOT_FOUND)

    # --- helpers -----------------------------------------------------------
    def _serve_json(self, payload: dict, status: int = HTTPStatus.OK):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

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
                 secure: bool = False):
        self._host = host
        self._port = port
        self._collector = NavigationSystemCollector(grpc_address, grpc_port, secure)
        # The request handler is re-instantiated per connection; expose the
        # collector through a subclass so each handler has access to it.
        handler_cls = type("BoundRequestHandler", (_RequestHandler,),
                           {"collector": self._collector, "web_server": self})
        self._httpd = ThreadingHTTPServer((host, port), handler_cls)

    def serve_forever(self):
        _logger.info(f"Navigation web server listening on http://{self._host}:{self._port}")
        _logger.info(f"Connecting to gRPC agent at {self._collector.agent_address} "
                     f"(secure={self._collector._secure})")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            _logger.info("Navigation web server stopping (KeyboardInterrupt)")
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

    server = NavigationWebServer(
        host=options.address,
        port=options.port,
        grpc_address=options.grpc_address,
        grpc_port=options.grpc_port,
        secure=secure,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(web_main())
