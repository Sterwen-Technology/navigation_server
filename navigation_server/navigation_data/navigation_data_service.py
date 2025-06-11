#-------------------------------------------------------------------------------
# Name:        generic service classes for data
#
# Author:      Laurent Carré
#
# Created:     09/06/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
from collections import namedtuple

from navigation_server.router_common import CANGrpcStreamReader, NavThread
from navigation_server.router_core import NMEA2000Msg
from navigation_server.nmea2000 import get_n2k_decoded_object
from navigation_server.generated.nmea2000_pb2 import nmea2000pb


_logger = logging.getLogger("ShipDataServer." + __name__)


ProcessVector = namedtuple('ProcessVector', ['subscriber', 'msg_id', 'vector'])


class NavigationDataService(NavThread):
    """
    Handles the navigation data service by utilizing a thread-based implementation to
    process and dispatch navigation data using Protocol Group Numbers (PGNs).

    The NavigationDataService class is responsible for subscribing to specific navigation
    data streams, processing those streams, and dispatching the data via provided callback
    functions. It interfaces with a CAN gRPC stream reader to process navigation data
    protobuf messages and utilizes a dispatch table to map PGNs to processing vectors.
    """

    def __init__(self, opts):
        """
        Initialize an instance of the class with given options.

        Attributes:
        name (str): The name of the object, extracted from the options.
        input_stream (CANGrpcStreamReader): A stream reader initialized with the name
            and options provided.
        dispatch_table (dict): A table for dispatching tasks or handlers.
        stop_flag (bool): A flag indicating whether the process should be stopped.

        Parameters:
        opts (dict): A dictionary containing configuration options. opts shall include the parameters to read from the CAN stream.
        see class: CANGrpcStreamReader documentation
        """
        self._name = opts['name']
        super().__init__(self._name)
        self._input_stream = CANGrpcStreamReader(self._name, opts)
        self._dispatch_table = {}
        self._stop_flag = False

    def subscribe(self, subscriber, pgn:int, vector):
        """
        Subscribes a subscriber to a process vector associated with a given PGN and vector.

        This method is used to associate a subscriber with a specific process vector
        identified by a PGN (Parameter Group Number) and a vector. It initializes the process
        vector and updates the dispatch table with the provided PGN as the key.

        Args:
            subscriber: The subscriber to be associated with the process vector. The type of
                this parameter would depend on the implementation of the `ProcessVector` class.
            pgn (int): The Parameter Group Number (PGN) associated with the process vector.
            vector: The data or configuration associated with the process vector. Its type
                would also depend on the implementation of the `ProcessVector` class.
        """
        process_vector = ProcessVector(subscriber, pgn, vector)
        self._dispatch_table[pgn] = process_vector

    def finalize(self):
        super().start()

    def nrun(self):

        while not self._stop_flag:
            # start or restart input stream
            if self._input_stream.start_stream_to_callback(self.process_can_protobuf):
                self._input_stream.wait_for_stream()

    def process_can_protobuf(self, pb_msg:nmea2000pb):
        try:
            vector = self._dispatch_table[pb_msg.pgn].vector
        except KeyError:
            _logger.debug("NavigationDataService no processing vector for PGN %d" % pb_msg.pgn)
            return
        # now convert to actual decoded PGN object
        n2k_msg = NMEA2000Msg(pgn=pb_msg.pgn, protobuf=pb_msg)
        decoded_msg = get_n2k_decoded_object(n2k_msg)
        try:
            vector(decoded_msg)
        except Exception as err:
            _logger.error(f"Exception while processing PGN:{decoded_msg.pgn}: {err}")

    def stop_service(self):
        self._input_stream.close()
        self._stop_flag = True


