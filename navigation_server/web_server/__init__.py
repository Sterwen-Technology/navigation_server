#-------------------------------------------------------------------------------
# Name:        package web_server
# Purpose:     Web interface for navigation_server, accessing gRPC servers
#
#              This package has been refactored into three main components:
#              1. user_management.py - User authentication and session management
#              2. data_collectors.py - Data collection layer with collectors for each service
#              3. web_server.py - HTTP server implementation
#
#              The web_top_server.py provides integration with the server_main.py
#              as a standalone process.
#
# Author:      Vibe Code
#
# Created:     15/08/2025
# Refactored:  25/09/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

# Main exports for backward compatibility
from .web_server import NavigationWebServer, web_main
from .web_top_server import WebTopServer

# User management exports
from .user_management import UserStore, Authenticator, _NullUserStore, DEFAULT_SESSION_TIMEOUT

# Data collectors exports
from .data_collectors import (
    NavigationSystemCollector,
    ProcessCollector,
    BaseServiceCollector,
    NetworkServiceCollector,
    ConsoleServiceCollector,
    NMEA2000ServiceCollector,
    EngineServiceCollector,
    MPPTServiceCollector,
    EnergyServiceCollector,
    BatteryServiceCollector,
)
