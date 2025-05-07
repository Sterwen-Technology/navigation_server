#-------------------------------------------------------------------------------
# Name:        package navigation_clients
# Purpose:
#
# Author:      Laurent Carré
#
# Created:    07/02/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


from .console_client import *
from .energy_client import MPPT_Client, MPPT_device_proxy, MPPT_output_proxy
from .nmea_server_client import GrpcNmeaServerClient
from .navigation_data_client import EngineClient
from .network_client import NetworkClient, NetworkStatusProxy, NetConnectionProxy, NetInterfaceProxy
from .n2k_can_client import NMEA2000CanClient