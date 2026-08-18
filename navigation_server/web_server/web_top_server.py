#-------------------------------------------------------------------------------
# Name:        web_top_server
# Purpose:     Web interface server integrated in the navigation_server runtime
#
#              WebTopServer is the main server of a process launched by
#              server_main.py. It is a subclass of GenericTopServer and uses the
#              main thread to run the blocking HTTP server (serve_forever).
#
#              This is the "solution a)" integration: the web server is the
#              sole server of the process, which prevents the creation of other
#              servers/services/couplers in the same process (strict control).
#
# Author:      Vibe Code
#
# Created:     17/08/2025
# Copyright:   (c) Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.router_common import MessageServerGlobals, GenericTopServer
from navigation_server.router_common.configuration import Parameters
from .server import NavigationWebServer

_logger = logging.getLogger("ShipDataServer." + __name__)


class WebTopServer(GenericTopServer):
    """Main server for the web interface process.

    Instantiated from the Yaml configuration with a single Parameters
    argument (the canonical interface). The web server uses the main thread:
    start() prepares the HTTP server and wait() enters the blocking
    serve_forever() loop. stop() (triggered by SIGINT) shuts the HTTP
    server down.

    The TLS mode for the gRPC connections to the agent is inherited from
    the global configuration (MessageServerGlobals.configuration.
    secure_communications); the CA certificate is already loaded by
    server_main before the objects are built.
    """

    def __init__(self, opts: Parameters):
        super().__init__(opts)
        self._name = 'web_top_server'
        MessageServerGlobals.main_server = self
        self._web_server = None

        web_port = opts.get('port', int, 4545)
        web_host = opts.get('host', str, "0.0.0.0")
        grpc_address = opts.get('grpc_address', str, "127.0.0.1")
        grpc_port = opts.get('grpc_port', int, 4545)

        # The secure flag is inherited from the global configuration so the
        # web server connects to the agent with the same TLS policy as the
        # rest of the deployment.
        config = MessageServerGlobals.configuration
        secure = config.secure_communications

        self._web_server = NavigationWebServer(
            host=web_host,
            port=web_port,
            grpc_address=grpc_address,
            grpc_port=grpc_port,
            secure=secure,
        )

    def start(self) -> bool:
        # The HTTP server itself is not started here; it is started in wait()
        # because serve_forever() blocks the main thread. We only signal that
        # the server is ready.
        self._is_running = True
        import datetime
        self._start_time = datetime.datetime.now()
        self._start_time_s = self._start_time.strftime("%Y/%m/%d-%H:%M:%S")
        _logger.info("Web server ready on http://%s:%d (main thread)"
                     % (self._web_server._host, self._web_server._port))
        return True

    def wait(self):
        # Blocks the main thread until the HTTP server stops (SIGINT or
        # explicit stop).
        self._web_server.serve_forever()
        _logger.info("Web server main loop ended")
        self._is_running = False

    def stop_server(self):
        _logger.info("Stopping web server")
        self._web_server.stop()

    @property
    def console_present(self):
        # No console service for a pure web server process.
        return False

    def is_agent(self):
        return False
