#-------------------------------------------------------------------------------
# Name:        package router_common
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     26/02/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
from .global_variables import (MessageServerGlobals, find_pgn, manufacturer_name, Typedef, resolve_ref, resolve_class,
                               set_global_var, get_global_var, set_hook, test_exec_hook, get_global_option,
                               get_global_enum, set_root_package)
from .arguments import init_options
from .date_time_utilities import format_timestamp
from .global_exceptions import *
from .generic_msg import *
from .log_utilities import NavigationLogSystem
from .network_utils import get_id_from_mac, get_mac
from .object_utilities import copy_attribute, build_subclass_dict
from .protobuf_utilities import (pb_enum_string, set_protobuf_data, ProtobufProxy, GrpcAccessException,
                                 copy_protobuf_data)
from .protob_arguments import protob_to_dict, dict_to_protob
from .xml_utilities import XMLDefinitionFile, XMLDecodeError
from .configuration import NavigationConfiguration
from .message_trace import MessageTraceError, NMEAMsgTrace
from .server_common import NavigationServer
from .grpc_server_service import GrpcServer, GrpcService, GrpcServerError, GrpcSecondaryService
from .generic_top_server import GenericTopServer
from .nav_threading import NavThread, NavThreadingController, NavProfilingController
from .constants_conversion import nautical_mille, mps_to_knots, n2ktime_to_datetime, radian_to_deg
