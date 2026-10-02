#-------------------------------------------------------------------------------
# Name:        web_server
# Purpose:     Web interface HTTP server for navigation_server
#
#              This module provides a lightweight HTTP server (based on the
#              standard library) that exposes a JSON API and a single-page web
#              frontend. It uses the data collectors to access the
#              navigation_server gRPC services.
#
# Author:      Vibe Code
#
# Created:     25/09/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import argparse
import json
import logging
import os
import uuid
import queue
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from navigation_server.router_common import GrpcClient, MessageServerGlobals
from navigation_server.generated.energy_pb2 import EnergyControllerData, EnergyControllerParameters, BatteryBank, battery_in_out, BatteryUnit, EnergySourceDevice, EnergySourceData
from navigation_server.generated.network_pb2 import NetInterface as NetInterfacePb

from .user_management import Authenticator, UserStore, _NullUserStore, DEFAULT_SESSION_TIMEOUT, _SESSION_COOKIE
from .data_collectors import NavigationSystemCollector

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


def _parse_api_path(path: str):
    """Parse an API path and extract service_handle and parameters.
    
    API paths follow the pattern: /api/{service_handle}/{parameters...}
    
    Args:
        path: The full request path
        
    Returns:
        tuple: (service_handle, parameters_list) or (None, None) if not an API path
    """
    if not path.startswith("/api/"):
        return None, None
    
    # Remove /api/ prefix and strip trailing slash
    path_parts = path[len("/api/"):].rstrip("/").split("/")
    
    if not path_parts or not path_parts[0]:
        return None, None
    
    service_handle = path_parts[0]
    # Filter out empty strings from parameters (caused by double slashes or trailing slashes)
    parameters = [p for p in path_parts[1:] if p]
    
    return service_handle, parameters


class _RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler serving the JSON API and the static frontend."""

    # Shared collector set by NavigationWebServer before serving.
    collector: NavigationSystemCollector = None
    web_server = None  # type: NavigationWebServer | None
    authenticator = None  # type: Authenticator | None

    server_version = "NavigationWebServer/1.0"

    def log_message(self, format, *args):  # noqa: A002 - signature from stdlib
        _logger.debug("%s - %s" % (self.address_string(), format % args))

    # --- routing -----------------------------------------------------------
    def do_GET(self):  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        parsed_url = urlparse(self.path)
        
        if path == "/" or path == "/index.html":
            self._serve_static("index.html", "text/html; charset=utf-8")
        elif path == "/api/login":
            self._serve_login_status()
        elif path == "/health":
            self._serve_json({"ok": True, "time": time.time(), "agent_connected": self.collector._server.connected})
        elif path == "/api/config":
            self._serve_config()
        elif not self._authorized(path):
            self._unauthorized()
            return
        else:
            # Parse API path
            service_handle, parameters = _parse_api_path(path)
            
            if service_handle is not None:
                # Special handling for log/stream which uses SSE
                if service_handle == "log" and len(parameters) >= 2 and parameters[0] == "stream":
                    process_name = parameters[1] if len(parameters) >= 2 else None
                    if process_name:
                        self._serve_log_stream(process_name)
                    else:
                        self._serve_json({"ok": False, "error": "missing process name"},
                                         status=HTTPStatus.BAD_REQUEST)
                    return
                
                if service_handle == "process" and len(parameters) >= 3 and parameters[1] == "log" and parameters[2] == "stream":
                    process_name = parameters[0]
                    self._serve_log_stream(process_name)
                    return
                
                # Extract query parameters from URL
                query_params = parsed_url.query
                kwargs = {}
                if query_params:
                    # Parse query parameters if needed
                    from urllib.parse import parse_qs
                    parsed_qs = parse_qs(query_params)
                    for key, value in parsed_qs.items():
                        kwargs[key] = value[0] if len(value) == 1 else value
                
                try:
                    result = self.collector.service_execution(service_handle, parameters, **kwargs)
                    self._serve_json(result)
                except Exception as e:
                    _logger.error(f"Error executing service {service_handle}: {e}")
                    self._serve_json({"ok": False, "error": f"Service execution failed: {str(e)}"},
                                     status=HTTPStatus.INTERNAL_SERVER_ERROR)
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
        
        # Parse API path
        service_handle, parameters = _parse_api_path(path)
        
        if service_handle is None:
            self._serve_json({"ok": False, "error": "not found"},
                             status=HTTPStatus.NOT_FOUND)
            return
        
        # Read body for POST requests
        body = self._read_json_body()
        if body is None:
            return
        
        # Delegate to collector with body as kwargs
        try:
            result = self.collector.service_execution(service_handle, parameters, **body)
            self._serve_json(result)
        except Exception as e:
            _logger.error(f"Error executing service {service_handle}: {e}")
            self._serve_json({"ok": False, "error": f"Service execution failed: {str(e)}"},
                             status=HTTPStatus.INTERNAL_SERVER_ERROR)

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
        disconnects or the stream ends. Supports multiple concurrent connections
        by tracking active connections and only stopping the stream when the last
        connection for a process disconnects.
        """
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        # Generate a unique connection ID
        connection_id = str(uuid.uuid4())
        
        # Track this connection
        with self.web_server._active_log_connections_lock:
            if process_name not in self.web_server._active_log_connections:
                self.web_server._active_log_connections[process_name] = set()
            self.web_server._active_log_connections[process_name].add(connection_id)
        
        line_queue = queue.Queue(maxsize=200)
        client_disconnected = [False]

        def on_line(msg):
            try:
                # msg is a LogLines protobuf; extract the line string
                line_text = msg.line if hasattr(msg, 'line') else str(msg)
                line_queue.put_nowait(line_text)
            except queue.Full:
                pass

        # Start the gRPC log stream only if this is the first connection for this process
        should_start_stream = False
        with self.web_server._active_log_connections_lock:
            if len(self.web_server._active_log_connections[process_name]) == 1:
                should_start_stream = True
        
        if should_start_stream:
            started = self.collector.start_log_stream(process_name, on_line)
            if not started:
                # Remove our connection tracking since we failed to start
                with self.web_server._active_log_connections_lock:
                    self.web_server._active_log_connections[process_name].discard(connection_id)
                    if not self.web_server._active_log_connections[process_name]:
                        del self.web_server._active_log_connections[process_name]
                
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
            # Remove this connection from tracking
            with self.web_server._active_log_connections_lock:
                if process_name in self.web_server._active_log_connections:
                    self.web_server._active_log_connections[process_name].discard(connection_id)
                    # Only stop the stream if this was the last connection for this process
                    if not self.web_server._active_log_connections[process_name]:
                        del self.web_server._active_log_connections[process_name]
                        self.collector.stop_log_stream(process_name)

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
        self._active_log_connections = {}  # process_name -> set of connection ids
        self._active_log_connections_lock = threading.Lock()
        # The request handler is re-instantiated per connection; expose the
        # collector and authenticator through a subclass so each handler has
        # access to them.
        handler_cls = type("BoundRequestHandler", (_RequestHandler,),
                           {"collector": self._collector, "web_server": self,
                            "authenticator": self._authenticator})
        try:
            self._httpd = ThreadingHTTPServer((host, port), handler_cls)
        except OSError as e:
            _logger.error(f"Cannot create HTTP server on {host}:{port}: {e}")
            raise RuntimeError(f"Socket error: cannot bind to {host}:{port}") from e

    def serve_forever(self):
        _logger.info(f"Navigation web server listening on http://{self._host}:{self._port}")
        _logger.info(f"Connecting to gRPC agent at {self._collector.agent_address} "
                     f"(secure={self._collector.secure})")

        self._httpd.serve_forever()
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
