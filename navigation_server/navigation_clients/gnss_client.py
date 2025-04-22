#-------------------------------------------------------------------------------
# Name:        GNSS client
# Purpose:     Access to gRPC GNSS Service
#
# Author:      Laurent Carré
#
# Created:     19/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.set_logging_root import nav_logging_root
from navigation_server.generated.gnss_pb2_grpc import GNSSServiceStub, GNSS_Status, request
from router_common.client_common import GrpcClient, ServiceClient

_logger = logging.getLogger(nav_logging_root + __name__)

class GNSSStatusProxy:

    def __init__(self, gnss_status:GNSS_Status):
        self._gnss_status = gnss_status

    @property
    def fixed(self):
        return self._gnss_status.fixed

    @property
    def fix_time(self) -> float:
        return self._gnss_status.fix_time

    @property
    def gnss_time(self) -> str:
        return self._gnss_status.gnss_time

    @property
    def nb_satellites_in_fix(self) -> int:
        return self._gnss_status.nb_satellites_in_fix


class GNSSClient(ServiceClient):

    def __init__(self) :
        super().__init__(GNSSServiceStub)

    def gnss_status(self) -> GNSSStatusProxy:
        _logger.debug("GNSS status request")
        return self._server_call(self._stub.gnss_status, request(), GNSSStatusProxy)



