#-------------------------------------------------------------------------------
# Name:        navigation_database
# Purpose:     RT database collecting the navigation parameters
#
# Author:      Laurent Carré
#
# Created:     15/02/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.router_common import GrpcService


_logger = logging.getLogger("ShipDataServer."+__name__)

class NavigationDatabase(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._source = opts.get('source', str, None)
        if self._source is None:
            _logger.error("Navigation database source not specified")
            raise ValueError("Navigation database source not specified")
        self._source_function = None


